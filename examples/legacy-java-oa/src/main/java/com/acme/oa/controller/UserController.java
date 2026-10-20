package com.acme.oa.controller;

import com.acme.oa.service.UserService;
import org.springframework.web.bind.annotation.*;

/** 用户管理 */
@RestController
@RequestMapping("/user")
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    /** 新增用户 */
    @PostMapping("/add")
    public void add(@RequestParam String id, @RequestParam String name, @RequestParam long deptId) {
        userService.add(id, name, deptId);
    }

    /** 停用用户（离职） */
    @PostMapping("/disable")
    public void disable(@RequestParam String id) {
        userService.disable(id);
    }
}
