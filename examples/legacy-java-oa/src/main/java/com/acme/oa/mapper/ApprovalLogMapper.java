package com.acme.oa.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface ApprovalLogMapper {
    void insert(@Param("leaveId") long leaveId, @Param("operator") String operator, @Param("action") String action, @Param("comment") String comment);
}
