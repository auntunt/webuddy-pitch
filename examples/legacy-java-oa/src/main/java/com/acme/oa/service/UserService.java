package com.acme.oa.service;

import com.acme.oa.mapper.UserMapper;
import com.acme.oa.util.PasswordUtil;
import org.springframework.stereotype.Service;

@Service
public class UserService {
    private final UserMapper userMapper;

    public UserService(UserMapper userMapper) {
        this.userMapper = userMapper;
    }

    public void add(String id, String name, long deptId) {
        if (userMapper.selectById(id) != null) {
            throw new IllegalArgumentException("工号已存在");
        }
        userMapper.insert(id, name, deptId);
    }

    /** 停用后该用户不能再提交报销，但历史单据保留 */
    public void disable(String id) {
        userMapper.disable(id);
    }
}
