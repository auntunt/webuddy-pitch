"""Go projects: gin routes, GORM tables and package/method calls make the same business flows as Java."""
import shutil
import tempfile
import unittest
from pathlib import Path

from tmh import codeindex, flow, golang, graph, mapper

FILES = {
    "go.mod": "module github.com/acme/shop\n\ngo 1.22\n",
    "main.go": '''package main

import (
	"github.com/acme/shop/model"
	"github.com/acme/shop/router"
	"github.com/gin-gonic/gin"
)

func main() {
	go model.SyncOrders(60)
	r := gin.Default()
	router.SetApiRouter(r)
}
''',
    "router/api.go": '''package router

import (
	"github.com/acme/shop/controller"
	"github.com/acme/shop/middleware"
	"github.com/gin-gonic/gin"
)

func SetApiRouter(router *gin.Engine) {
	api := router.Group("/api")
	{
		orderRoute := api.Group("/order")
		orderRoute.Use(middleware.UserAuth())
		{
			orderRoute.POST("/", middleware.Limit(), controller.AddOrder)
			orderRoute.PUT("/:id/pay", controller.PayOrder)
		}
		api.GET("/status", func(c *gin.Context) {})
	}
}
''',
    "controller/order.go": '''package controller

import (
	"net/http"

	"github.com/acme/shop/model"
	svc "github.com/acme/shop/service"
	"github.com/gin-gonic/gin"
)

// AddOrder 下单
func AddOrder(c *gin.Context) {
	order := model.Order{}
	if err := c.ShouldBindJSON(&order); err != nil {
		c.JSON(http.StatusOK, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if order.Amount <= 0 {
		common_error(c, "金额必须大于零")
		return
	}
	if err := svc.PlaceOrder(&order); err != nil {
		return
	}
}

// PayOrder 支付订单
func PayOrder(c *gin.Context) {
	o, err := model.GetOrderById(c.Param("id"))
	if err != nil {
		return
	}
	o.MarkPaid()
}

func common_error(c *gin.Context, msg string) {}
''',
    "service/order.go": '''package service

import (
	"github.com/acme/shop/model"
)

// PlaceOrder 校验库存并落单
func PlaceOrder(o *model.Order) error {
	return o.Insert()
}
''',
    "model/order.go": '''package model

import (
	"gorm.io/gorm"
)

const (
	OrderStatusPaid = 2 // paid
)

type Order struct {
	gorm.Model
	UserId int    `json:"user_id" gorm:"index"`
	Amount int64  `json:"amount"`
	Status int    `json:"status"`
}

type OrderItem struct {
	OrderId int `gorm:"index"`
	Sku     string
}

func (OrderItem) TableName() string {
	return "order_lines"
}

func (o *Order) Insert() error {
	return DB.Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(o).Error; err != nil {
			return err
		}
		return tx.Create(&OrderItem{OrderId: int(o.ID)}).Error
	})
}

func GetOrderById(id string) (*Order, error) {
	var o Order
	err := DB.Where("id = ?", id).First(&o).Error
	return &o, err
}

func (o *Order) MarkPaid() {
	DB.Model(o).
		Where("status = ?", 1).
		Update("status", OrderStatusPaid)
}

func SyncOrders(sec int) {
	var orders []*Order
	DB.Find(&orders)
	DB.Exec(`DELETE FROM order_lines WHERE order_id = 0`)
}
''',
    "model/main.go": '''package model

import "gorm.io/gorm"

var DB *gorm.DB
''',
    "model/order_test.go": '''package model

func TestX() {}
''',
}


class GoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="tmh-go-"))
        for p, t in FILES.items():
            (cls.root / p).parent.mkdir(parents=True, exist_ok=True)
            (cls.root / p).write_text(t, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_index_models_packages_and_types(self):
        idx = codeindex.build_index(self.root)
        cs = idx["classes"]
        self.assertEqual(cs["model"][0]["kind"], "package")
        self.assertIn("GetOrderById", cs["model"][0]["methods"])
        order = cs["model.Order"][0]
        self.assertEqual(order["kind"], "struct")
        self.assertEqual(set(order["methods"]), {"Insert", "MarkPaid"})
        self.assertIn("Status", order["fields"])
        add = cs["controller"][0]["methods"]["AddOrder"][0]
        self.assertEqual(add["comment"], "下单")  # "AddOrder" left off the doc comment
        self.assertEqual(add["params"]["order"], "model.Order")
        self.assertEqual(add["params"]["svc"], "service")  # import alias → package
        pay = cs["controller"][0]["methods"]["PayOrder"][0]
        self.assertEqual(pay["params"]["o"], "model.Order")  # through GetOrderById's result type
        self.assertFalse([k for k in cs if "Test" in k])  # _test.go stays out

    def test_map_reads_routes_tables_and_background_work(self):
        m = mapper.build_map(self.root)
        eps = {(e["method"], e["path"]): e["handler"] for e in m["endpoints"]}
        self.assertEqual(eps[("POST", "/api/order/")], "controller.AddOrder")
        self.assertEqual(eps[("PUT", "/api/order/:id/pay")], "controller.PayOrder")
        self.assertNotIn(("GET", "/api/status"), eps)  # an inline func is not a handler to trace
        ent = {e["class"]: e["table"] for e in m["entities"]}
        self.assertEqual(ent, {"Order": "ORDERS", "OrderItem": "ORDER_LINES"})
        self.assertIn("ORDER_LINES", m["tables"])
        self.assertEqual([(j["kind"], j["class"]) for j in m["jobs"]], [("后台协程", "model.SyncOrders")])
        self.assertEqual(golang.default_table("UserGroup"), "USER_GROUPS")
        self.assertEqual(golang.default_table("QuotaData"), "QUOTA_DATA")

    def test_flows_follow_calls_into_gorm(self):
        fl = {f["trigger"]: f for f in flow.build_flows(self.root)["flows"]}
        add = fl["POST /api/order/"]
        self.assertEqual(add["name"], "下单")
        keys = [n["key"] for n in add["nodes"]]
        self.assertIn("service.PlaceOrder", keys)
        self.assertIn("model.Order.Insert", keys)
        self.assertEqual(add["crud"], {"ORDERS": "C", "ORDER_LINES": "C"})
        self.assertTrue(add["transactions"])
        self.assertEqual([r["message"] for r in add["rules"]], ["参数错误", "金额必须大于零"])
        pay = fl["PUT /api/order/:id/pay"]
        self.assertEqual(pay["crud"], {"ORDERS": "RU"})
        st = pay["states"][0]
        self.assertEqual((st["table"], st["column"], st["to"]), ("ORDERS", "STATUS", "OrderStatusPaid=2"))
        job = [f for f in fl.values() if f["kind"] == "定时任务"][0]
        self.assertEqual(job["crud"], {"ORDERS": "R", "ORDER_LINES": "D"})

    def test_graph_builds_for_go(self):
        r = graph.build(self.root, use_cache=False)
        self.assertEqual(r["kinds"].get("flow"), 3)
        g = graph.Graph(self.root)
        self.assertTrue(g.node("fn:controller.AddOrder"))
        self.assertTrue(g.out("fn:model.Order.Insert", "writes"))
        self.assertEqual(g.node("fn:controller.AddOrder")["data"]["bkey"], "order")
