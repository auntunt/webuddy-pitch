package com.jsh.erp.verification;

import com.jsh.erp.service.SequenceService;
import com.jsh.erp.datasource.mappers.SequenceMapperEx;
import com.jsh.erp.utils.RedisLockUtil;
import com.jsh.erp.exception.BusinessRunTimeException;
import org.junit.Before;
import org.junit.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.mockito.InOrder;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;

public class SequenceServiceTest {
    private SequenceService service;
    private SequenceMapperEx database;
    private RedisLockUtil lock;
    @Before public void setup() throws Exception {
        service=new SequenceService();database=mock(SequenceMapperEx.class);lock=mock(RedisLockUtil.class);
        ReflectionTestUtils.setField(service,"sequenceMapperEx",database);
        ReflectionTestUtils.setField(service,"redisLockUtil",lock);
        when(lock.tryLock(anyString(),anyString(),anyLong(),anyLong())).thenReturn(true);
        when(database.getBuildOnlyNumber(anyString())).thenReturn(123L);
    }
    @Test public void locksBeforeUpdatingAndAlwaysUnlocks() throws Exception {
        String number=service.buildOnlyNumber();assertTrue(number.matches("0*123"));
        InOrder ordered=inOrder(lock,database);
        ordered.verify(lock).tryLock(anyString(),anyString(),eq(3000L),eq(100L));
        ordered.verify(database).updateBuildOnlyNumber();
        ordered.verify(database).getBuildOnlyNumber(anyString());
        ordered.verify(lock).unlock(anyString(),anyString());
    }
    @Test public void lockContentionDoesNotWriteDatabase() throws Exception {
        when(lock.tryLock(anyString(),anyString(),anyLong(),anyLong())).thenReturn(false);
        try {service.buildOnlyNumber();fail("expected lock conflict");}catch(BusinessRunTimeException expected) { }
        verifyZeroInteractions(database);verify(lock,never()).unlock(anyString(),anyString());
    }
    @Test public void databaseFailureStillReleasesOwnedLock() throws Exception {
        doThrow(new RuntimeException("synthetic database failure")).when(database).updateBuildOnlyNumber();
        try {service.buildOnlyNumber();fail("expected database failure");}catch(BusinessRunTimeException expected) { }
        verify(lock).unlock(anyString(),anyString());
    }
    @Test public void interruptedLockPreservesInterruptAndDoesNotUnlockForeignLock() throws Exception {
        when(lock.tryLock(anyString(),anyString(),anyLong(),anyLong())).thenThrow(new InterruptedException("synthetic"));
        try {service.buildOnlyNumber();fail("expected interruption");}catch(BusinessRunTimeException expected) {assertTrue(Thread.currentThread().isInterrupted());}
        finally {Thread.interrupted();}
        verifyZeroInteractions(database);verify(lock,never()).unlock(anyString(),anyString());
    }
    @Test public void lockUsesSameOwnershipTokenWhenReleased() throws Exception {
        service.buildOnlyNumber();
        org.mockito.ArgumentCaptor<String> token=org.mockito.ArgumentCaptor.forClass(String.class);
        verify(lock).tryLock(anyString(),token.capture(),anyLong(),anyLong());
        verify(lock).unlock(anyString(),eq(token.getValue()));
    }
}
