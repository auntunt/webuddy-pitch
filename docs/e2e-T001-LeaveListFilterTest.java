package com.acme.oa;

import com.acme.oa.mapper.LeaveMapper;
import com.acme.oa.service.LeaveService;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** /leave/list 筛选需求的特征测试：不传 status 时行为必须与旧版一致 */
class LeaveListFilterTest {

    private static String renderSelectPage(Map<String, Object> params) throws Exception {
        Configuration cfg = new Configuration();
        try (InputStream in = LeaveListFilterTest.class.getResourceAsStream("/mapper/LeaveMapper.xml")) {
            new XMLMapperBuilder(in, cfg, "mapper/LeaveMapper.xml", cfg.getSqlFragments()).parse();
        }
        BoundSql sql = cfg.getMappedStatement("com.acme.oa.mapper.LeaveMapper.selectPage").getBoundSql(params);
        return sql.getSql().replaceAll("\\s+", " ");
    }

    private static Map<String, Object> pageParams() {
        Map<String, Object> p = new HashMap<>();
        p.put("start", 0);
        p.put("end", 20);
        return p;
    }

    @Test
    void withoutStatusServiceUsesTwentyPerPage() {
        LeaveMapper mapper = Mockito.mock(LeaveMapper.class);
        new LeaveService(mapper).list(2);
        Mockito.verify(mapper).selectPage(20, 40, null);
    }

    @Test
    void blankStatusIsTreatedAsNoFilter() {
        LeaveMapper mapper = Mockito.mock(LeaveMapper.class);
        new LeaveService(mapper).list(1, "   ");
        Mockito.verify(mapper).selectPage(0, 20, null);
    }

    @Test
    void statusIsTrimmedAndPassedToMapper() {
        LeaveMapper mapper = Mockito.mock(LeaveMapper.class);
        new LeaveService(mapper).list(1, " APPROVED ");
        Mockito.verify(mapper).selectPage(0, 20, "APPROVED");
    }

    @Test
    void statusSqlUsesBoundParameter() throws Exception {
        Map<String, Object> p = pageParams();
        p.put("status", "PENDING");
        String sql = renderSelectPage(p);
        assertTrue(sql.contains("AND l.STATUS = ?"), sql);
        assertFalse(sql.contains("PENDING"), sql);
    }

    @Test
    void withoutStatusSqlHasNoStatusCondition() throws Exception {
        String sql = renderSelectPage(pageParams());
        assertFalse(sql.contains("l.STATUS"), sql);
        assertTrue(sql.contains("ORDER BY l.CREATED DESC"), sql);
    }
}
