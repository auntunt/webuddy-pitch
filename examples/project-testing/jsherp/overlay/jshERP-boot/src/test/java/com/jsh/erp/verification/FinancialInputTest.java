package com.jsh.erp.verification;

import com.jsh.erp.utils.StringUtil;
import com.jsh.erp.utils.SqlUtil;
import com.jsh.erp.utils.QueryUtils;
import com.jsh.erp.exception.UtilException;
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Collections;
import org.junit.Test;
import static org.junit.Assert.*;

public class FinancialInputTest {
    @Test public void sumsDecimalAmountsWithoutBinaryRounding() {
        assertEquals(0, new BigDecimal("0.30").compareTo(StringUtil.getArrSum(new String[]{"0.10", "0.20"})));
    }
    @Test public void sumsRefundsAndLargeAmountsExactly() {
        assertEquals(0, new BigDecimal("9999999999999999.99").compareTo(StringUtil.getArrSum(new String[]{"10000000000000000.00", "-0.01"})));
    }
    @Test public void emptyAmountListIsZero() { assertEquals(BigDecimal.ZERO, StringUtil.getArrSum(new String[]{})); }
    @Test(expected=NumberFormatException.class) public void malformedMoneyIsNotSilentlyZero() { StringUtil.getArrSum(new String[]{"12.00", "oops"}); }
    @Test public void preservesDecimalScaleWhenParsingList() { assertEquals(Arrays.asList(new BigDecimal("1.20"),new BigDecimal("-2.34")),StringUtil.strToBigDecimalList("1.20,-2.34")); }
    @Test public void numericIdentifierRejectsEmptyAndSignedInput() {
        assertTrue(StringUtil.isNumeric("100023"));
        for(String value:new String[]{"", "-1", "1.2", "1 OR 1=1", "abc"}) assertFalse(value,StringUtil.isNumeric(value));
        assertFalse(StringUtil.isNumeric(null));
    }
    @Test public void orderAllowsQualifiedColumnAndDirection() { assertEquals("h.create_time desc, h.id asc",SqlUtil.escapeOrderBySql("h.create_time desc, h.id asc")); }
    @Test public void orderRejectsInjectionSyntax() {
        for(String value:new String[]{"id; drop table jsh_user", "id--", "sleep(1)", "id/*comment*/", "id'"}) {
            try {SqlUtil.escapeOrderBySql(value); fail("accepted " + value);} catch(UtilException expected) { }
        }
    }
    @Test(expected=UtilException.class) public void orderRejectsExcessiveLength() { SqlUtil.escapeOrderBySql(String.join("", Collections.nCopies(501,"a"))); }
    @Test public void uniqueLookupReturnsTheOnlyRecord() { assertEquals("invoice",QueryUtils.list2One(Collections.singletonList("invoice"),"单据")); }
    @Test(expected=IllegalArgumentException.class) public void missingLookupDoesNotInventRecord() { QueryUtils.list2One(Collections.emptyList(),"单据"); }
    @Test(expected=IllegalArgumentException.class) public void ambiguousLookupDoesNotChooseFirst() { QueryUtils.list2One(Arrays.asList("invoice1","invoice2"),"单据"); }
}
