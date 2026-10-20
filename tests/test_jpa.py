"""Spring Data JPA, JPQL and runtime-chosen tables (decompiled legacy Spring MVC style)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tmh import flow  # noqa: E402

FILES = {
    "entity/Bill.java": '''package demo.entity;
import javax.persistence.*;
@Entity(name="to_bill")
@Table(name="to_bill")
public class Bill { private String id; private String status; }
''',
    "data/BillJpaRep.java": '''package demo.data;
public interface BillJpaRep extends PagingAndSortingRepository<Bill, String>, JpaSpecificationExecutor<Bill> {
    @Query(value="select u from to_bill u where status in (:sts)")
    public List<Bill> findByStatuses(@Param(value="sts") String[] var1);

    @Modifying
    @Query(value="update to_bill u set u.status = 'PAID' where u.status = 'APPROVED' and u.id = (:id)")
    public int markPaid(@Param(value="id") String var1);

    public Bill findByCode(String code);
}
''',
    "data/BillDao.java": '''package demo.data;
@Component
public class BillDao {
    @Autowired
    private JdbcTemplate jdbcTemplate;
    public void setStatus(String tablename, Bill bill) {
        String sql = "update " + tablename + " set status=" + bill.getStatus() + " where id='" + bill.getId() + "'";
        this.jdbcTemplate.update(sql);
    }
}
''',
    "entity/Const.java": '''package demo.entity;
public class Const {
    public static final String Bill_status_rejected = "9";
}
''',
    "web/BillController.java": '''package demo.web;
@Controller
@RequestMapping(value={"/bill"})
public class BillController {
    @Autowired
    private BillJpaRep billJpaRep;
    @Autowired
    private BillDao billDao;

    /** 新建报销单 */
    @RequestMapping(value={"/create"})
    @ResponseBody
    public Object create(String code) {
        Bill b = new Bill();
        this.billJpaRep.save(b);
        return b;
    }

    /** 支付完成 */
    @RequestMapping(value={"/pay"})
    @ResponseBody
    public Object pay(String id, String code) {
        Bill b = this.billJpaRep.findByCode(code);
        b.setStatus("PAID");
        if (code == null) {
            b.setStatus(Const.Bill_status_rejected);
        }
        this.billJpaRep.save(b);
        this.billJpaRep.markPaid(id);
        this.billDao.setStatus("to_bill_ext", b);
        return this.billJpaRep.findByStatuses(new String[]{"PAID"});
    }
}
''',
    "job/BaseJob.java": '''package demo.job;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
public abstract class BaseJob
implements Job {
    public abstract String doTask(JobExecutionContext var1);

    public void execute(JobExecutionContext context) {
        String result = this.doTask(context);
    }
}
''',
    "job/AutoPayJob.java": '''package demo.job;
public class AutoPayJob
extends BaseJob {
    @Autowired
    private BillJpaRep billJpaRep;

    @Override
    public String doTask(JobExecutionContext context) {
        this.billJpaRep.markPaid("1");
        return "ok";
    }
}
''',
}


class JpaFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp(prefix="tmh-jpa-"))
        for rp, text in FILES.items():
            p = cls.d / "src/main/java/demo" / rp
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        cls.flows = {f["handler"]: f for f in flow.build_flows(cls.d)["flows"]}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def test_save_of_new_entity_is_insert(self):
        self.assertEqual(self.flows["BillController.create"]["crud"], {"TO_BILL": "C"})

    def test_jpql_derived_and_dynamic_tables(self):
        f = self.flows["BillController.pay"]
        self.assertEqual(f["crud"]["TO_BILL"], "RU")
        self.assertIn("U", f["crud"]["〈动态:tablename〉"])
        st = {(s["table"], s["to"]) for s in f["states"]}
        self.assertIn(("TO_BILL", "PAID"), st)  # JPQL update, entity name mapped to table
        tr = [s for s in f["states"] if s["table"] == "TO_BILL" and s["to"] == "PAID" and s["from"] == ["APPROVED"]]
        self.assertTrue(tr)
        self.assertIn(("〈动态:tablename〉", "〈动态:bill.getStatus〉"), st)
        self.assertIn(("TO_BILL", "Bill_status_rejected=9"), st)  # setter on a typed entity, constant resolved
        self.assertNotIn("(代码)", {s["table"] for s in f["states"]})
        vias = {o["via"] for o in f["data_ops"]}
        self.assertTrue({"BillJpaRep.findByCode", "BillJpaRep.markPaid", "BillJpaRep.findByStatuses", "BillJpaRep.save"} <= vias)


    def test_job_registered_at_runtime_via_base_class(self):
        f = self.flows.get("AutoPayJob.doTask")
        self.assertIsNotNone(f, list(self.flows))
        self.assertEqual(f["kind"], "定时任务")
        self.assertIn("BaseJob", f["trigger"])
        self.assertEqual(f["crud"], {"TO_BILL": "U"})
        self.assertNotIn("BaseJob.doTask", self.flows)


if __name__ == "__main__":
    unittest.main()
