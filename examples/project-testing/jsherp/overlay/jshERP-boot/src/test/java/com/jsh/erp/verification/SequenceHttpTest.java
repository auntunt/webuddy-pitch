package com.jsh.erp.verification;

import com.jsh.erp.controller.SequenceController;
import com.jsh.erp.service.SequenceService;
import org.junit.Before;
import org.junit.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.test.util.ReflectionTestUtils;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class SequenceHttpTest {
    private MockMvc http;
    private SequenceService sequence;
    @Before public void setup() {
        SequenceController controller=new SequenceController();sequence=mock(SequenceService.class);
        ReflectionTestUtils.setField(controller,"sequenceService",sequence);
        http=MockMvcBuilders.standaloneSetup(controller).build();
    }
    @Test public void serializesGeneratedNumberWithoutLosingLeadingZeros() throws Exception {
        when(sequence.buildOnlyNumber()).thenReturn("000000123");
        http.perform(get("/sequence/buildNumber")).andExpect(status().isOk()).andExpect(jsonPath("$.code").value(200)).andExpect(jsonPath("$.data.defaultNumber").value("000000123"));
        verify(sequence,times(1)).buildOnlyNumber();
    }
    @Test public void databaseFailureIsNotSuccessfulBusinessResponse() throws Exception {
        when(sequence.buildOnlyNumber()).thenThrow(new RuntimeException("private database details"));
        http.perform(get("/sequence/buildNumber")).andExpect(status().isOk()).andExpect(jsonPath("$.code").value(500)).andExpect(jsonPath("$.data").value("获取数据失败"));
    }
    @Test public void unsupportedMethodDoesNotGenerateNumber() throws Exception {
        http.perform(post("/sequence/buildNumber")).andExpect(status().isMethodNotAllowed());verifyZeroInteractions(sequence);
    }
}
