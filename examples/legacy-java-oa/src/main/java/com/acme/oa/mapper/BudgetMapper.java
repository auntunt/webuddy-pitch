package com.acme.oa.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.math.BigDecimal;

@Mapper
public interface BudgetMapper {
    BigDecimal remaining(@Param("deptId") long deptId);
    int freeze(@Param("deptId") long deptId, @Param("amount") BigDecimal amount);
    int release(@Param("deptId") long deptId, @Param("amount") BigDecimal amount);
    int consume(@Param("deptId") long deptId, @Param("amount") BigDecimal amount);
}
