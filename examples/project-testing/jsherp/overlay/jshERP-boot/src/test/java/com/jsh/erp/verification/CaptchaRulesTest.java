package com.jsh.erp.verification;

import com.jsh.erp.service.UserService;
import com.jsh.erp.service.RedisService;
import com.jsh.erp.service.PlatformConfigService;
import com.jsh.erp.datasource.entities.PlatformConfig;
import com.jsh.erp.exception.BusinessRunTimeException;
import org.junit.Before;
import org.junit.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;

public class CaptchaRulesTest {
    private UserService service;
    private RedisService redis;
    private PlatformConfig config;
    @Before public void setup() throws Exception {
        service=new UserService();redis=mock(RedisService.class);PlatformConfigService settings=mock(PlatformConfigService.class);
        config=new PlatformConfig();config.setPlatformValue("1");when(settings.getInfoByKey("checkcode_flag")).thenReturn(config);
        ReflectionTestUtils.setField(service,"redisService",redis);ReflectionTestUtils.setField(service,"platformConfigService",settings);
    }
    @Test public void validCaptchaIsConsumed() throws Exception {
        when(redis.getCacheObject(anyString())).thenReturn("Ab12");service.validateCaptcha("ab12","fixture");
        verify(redis,times(1)).deleteObject(anyString());
    }
    @Test(expected=BusinessRunTimeException.class) public void missingCodeCannotLoginWhenRequired() throws Exception {service.validateCaptcha("","fixture");}
    @Test(expected=BusinessRunTimeException.class) public void missingChallengeCannotLoginWhenRequired() throws Exception {service.validateCaptcha("ab12","");}
    @Test public void wrongCodeIsRejectedAndConsumed() throws Exception {
        when(redis.getCacheObject(anyString())).thenReturn("Ab12");
        try{service.validateCaptcha("wrong","fixture");fail("accepted wrong code");}catch(BusinessRunTimeException expected) { }
        verify(redis).deleteObject(anyString());
    }
    @Test(expected=BusinessRunTimeException.class) public void expiredCodeIsRejected() throws Exception {service.validateCaptcha("ab12","expired");}
    @Test public void consumedChallengeCannotBeReplayed() throws Exception {
        when(redis.getCacheObject(anyString())).thenReturn("Ab12").thenReturn(null);service.validateCaptcha("Ab12","fixture");
        try{service.validateCaptcha("Ab12","fixture");fail("accepted replay");}catch(BusinessRunTimeException expected) { }
    }
    @Test public void explicitlyDisabledCaptchaDoesNotRequireRedisChallenge() throws Exception {
        config.setPlatformValue("0");service.validateCaptcha(null,null);verifyZeroInteractions(redis);
    }
}
