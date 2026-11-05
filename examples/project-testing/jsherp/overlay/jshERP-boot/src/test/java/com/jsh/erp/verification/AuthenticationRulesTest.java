package com.jsh.erp.verification;

import com.jsh.erp.service.UserService;
import com.jsh.erp.service.TenantService;
import com.jsh.erp.datasource.entities.User;
import com.jsh.erp.datasource.entities.UserExample;
import com.jsh.erp.datasource.entities.Tenant;
import com.jsh.erp.datasource.mappers.UserMapper;
import com.jsh.erp.utils.ExceptionCodeConstants.UserExceptionCode;
import java.util.Collections;
import java.util.Date;
import org.junit.Before;
import org.junit.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;

public class AuthenticationRulesTest {
    private UserService service;
    private UserMapper database;
    private TenantService tenants;
    private User user;
    private Tenant tenant;
    @Before public void setup() throws Exception {
        service=new UserService();database=mock(UserMapper.class);tenants=mock(TenantService.class);
        ReflectionTestUtils.setField(service,"userMapper",database);
        ReflectionTestUtils.setField(service,"tenantService",tenants);
        user=new User();user.setStatus((byte)0);user.setTenantId(42L);
        tenant=new Tenant();tenant.setEnabled(true);tenant.setExpireTime(new Date(System.currentTimeMillis()+86400000L));
        when(database.selectByExample(any(UserExample.class))).thenReturn(Collections.singletonList(user));
        when(tenants.getTenantByTenantId(42L)).thenReturn(tenant);
    }
    @Test public void validActiveAccountCanAuthenticate() throws Exception {assertEquals(UserExceptionCode.USER_CONDITION_FIT,service.validateUser("fixture","synthetic-hash"));}
    @Test public void unknownAccountIsRejected() throws Exception {
        when(database.selectByExample(any(UserExample.class))).thenReturn(Collections.emptyList());
        assertEquals(UserExceptionCode.USER_NOT_EXIST,service.validateUser("missing","synthetic-hash"));
    }
    @Test public void wrongPasswordIsRejected() throws Exception {
        when(database.selectByExample(any(UserExample.class))).thenReturn(Collections.singletonList(user)).thenReturn(Collections.emptyList());
        assertEquals(UserExceptionCode.USER_PASSWORD_ERROR,service.validateUser("fixture","wrong-hash"));
    }
    @Test public void disabledUserIsRejectedBeforePasswordLookup() throws Exception {
        user.setStatus((byte)1);assertEquals(UserExceptionCode.BLACK_USER,service.validateUser("fixture","synthetic-hash"));
        verify(database,times(1)).selectByExample(any(UserExample.class));
    }
    @Test public void disabledTenantIsRejected() throws Exception {
        tenant.setEnabled(false);assertEquals(UserExceptionCode.BLACK_TENANT,service.validateUser("fixture","synthetic-hash"));
    }
    @Test public void expiredTenantIsRejected() throws Exception {
        tenant.setExpireTime(new Date(1));assertEquals(UserExceptionCode.EXPIRE_TENANT,service.validateUser("fixture","synthetic-hash"));
    }
    @Test public void databaseOutageCannotAuthenticate() throws Exception {
        when(database.selectByExample(any(UserExample.class))).thenThrow(new RuntimeException("synthetic outage"));
        assertEquals(UserExceptionCode.USER_ACCESS_EXCEPTION,service.validateUser("fixture","synthetic-hash"));
    }
    @Test public void passwordQueryBindsCredentialsAndExcludesDeletedUsers() throws Exception {
        service.validateUser("fixture","synthetic-hash");
        org.mockito.ArgumentCaptor<UserExample> query=org.mockito.ArgumentCaptor.forClass(UserExample.class);
        verify(database,times(2)).selectByExample(query.capture());
        java.util.List<UserExample.Criterion> criteria=query.getAllValues().get(1).getOredCriteria().get(0).getAllCriteria();
        assertTrue(criteria.stream().anyMatch(c->"password =".equals(c.getCondition())&&"synthetic-hash".equals(c.getValue())));
        assertTrue(criteria.stream().anyMatch(c->"login_name =".equals(c.getCondition())&&"fixture".equals(c.getValue())));
        assertTrue(criteria.stream().anyMatch(c->"delete_flag <>".equals(c.getCondition())));
    }
}
