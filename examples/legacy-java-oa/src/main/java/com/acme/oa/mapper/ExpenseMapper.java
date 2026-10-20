package com.acme.oa.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@Mapper
public interface ExpenseMapper {
    List<Map<String, Object>> selectByUser(@Param("userId") String userId);
    Map<String, Object> selectById(@Param("id") long id);
    long nextId();
    void insert(@Param("id") long id, @Param("userId") String userId, @Param("deptId") long deptId, @Param("amount") BigDecimal amount, @Param("category") String category);
    int auditPass(@Param("id") long id, @Param("auditor") String auditor);
    int auditReject(@Param("id") long id, @Param("auditor") String auditor);
    int markPaid(@Param("id") long id, @Param("cashier") String cashier);
}
