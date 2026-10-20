package com.acme.oa.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.util.List;
import java.util.Map;

@Mapper
public interface LeaveMapper {
    List<Map<String, Object>> selectPage(@Param("start") int start, @Param("end") int end);
    long nextId();
    void insert(@Param("id") long id, @Param("applicant") String applicant, @Param("deptId") long deptId, @Param("days") int days, @Param("reason") String reason);
    int approve(@Param("id") long id, @Param("approver") String approver);
    int reject(@Param("id") long id, @Param("approver") String approver);
    int expireStale();
}
