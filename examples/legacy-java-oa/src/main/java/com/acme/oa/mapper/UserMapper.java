package com.acme.oa.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.util.Map;

@Mapper
public interface UserMapper {
    Map<String, Object> selectById(@Param("id") String id);
    void insert(@Param("id") String id, @Param("name") String name, @Param("deptId") long deptId);
    int disable(@Param("id") String id);
}
