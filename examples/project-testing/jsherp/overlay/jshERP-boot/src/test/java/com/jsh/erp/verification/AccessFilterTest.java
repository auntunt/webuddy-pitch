package com.jsh.erp.verification;

import com.jsh.erp.filter.LogCostFilter;
import com.jsh.erp.service.RedisService;
import javax.servlet.FilterChain;
import org.junit.Before;
import org.junit.Test;
import org.springframework.mock.web.MockFilterConfig;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;

public class AccessFilterTest {
    private LogCostFilter filter;
    private RedisService sessions;
    private FilterChain next;
    @Before public void setup() throws Exception {
        filter=new LogCostFilter();sessions=mock(RedisService.class);next=mock(FilterChain.class);
        ReflectionTestUtils.setField(filter,"redisService",sessions);
        MockFilterConfig config=new MockFilterConfig();config.addInitParameter("filterPath","/jshERP-boot/systemConfig/static");filter.init(config);
    }
    @Test public void anonymousInventoryReadDoesNotReachController() throws Exception {
        MockHttpServletRequest request=new MockHttpServletRequest("GET","/jshERP-boot/depotItem/list");MockHttpServletResponse response=new MockHttpServletResponse();
        filter.doFilter(request,response,next);verifyZeroInteractions(next);assertEquals("loginOut",response.getContentAsString());assertNotEquals(200,response.getStatus());
    }
    @Test public void anonymousWriteDoesNotReachController() throws Exception {
        MockHttpServletRequest request=new MockHttpServletRequest("POST","/jshERP-boot/depotHead/add");MockHttpServletResponse response=new MockHttpServletResponse();
        filter.doFilter(request,response,next);verifyZeroInteractions(next);assertNotEquals(200,response.getStatus());
    }
    @Test public void authenticatedRequestReachesControllerExactlyOnce() throws Exception {
        MockHttpServletRequest request=new MockHttpServletRequest("GET","/jshERP-boot/depotItem/list");MockHttpServletResponse response=new MockHttpServletResponse();
        when(sessions.getObjectFromSessionByKey(request,"userId")).thenReturn(42L);
        filter.doFilter(request,response,next);verify(next,times(1)).doFilter(request,response);
    }
    @Test public void pathTraversalIsDeniedEvenWithSession() throws Exception {
        for(String path:new String[]{"/jshERP-boot/../unit/list","/jshERP-boot/%2e%2e/unit/list","/jshERP-boot/%2E%2E/unit/list"}) {
            MockHttpServletRequest request=new MockHttpServletRequest("GET",path);MockHttpServletResponse response=new MockHttpServletResponse();
            when(sessions.getObjectFromSessionByKey(request,"userId")).thenReturn(42L);
            filter.doFilter(request,response,next);assertNotEquals(200,response.getStatus());
        }
        verifyZeroInteractions(next);
    }
    @Test public void loginEndpointRemainsReachableWithoutSession() throws Exception {
        MockHttpServletRequest request=new MockHttpServletRequest("POST","/jshERP-boot/user/login");MockHttpServletResponse response=new MockHttpServletResponse();
        filter.doFilter(request,response,next);verify(next).doFilter(request,response);
    }
}
