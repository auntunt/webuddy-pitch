package com.acme.oa.job;

import com.acme.oa.service.LeaveService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.io.FileWriter;

@Component
public class ReportJob {
    private final LeaveService leaveService;

    public ReportJob(LeaveService leaveService) {
        this.leaveService = leaveService;
    }

    /** 每晚导出请假汇总 */
    @Scheduled(cron = "0 0 2 * * ?")
    public void export() throws Exception {
        try (FileWriter w = new FileWriter("C:\\reports\\leave.csv")) {
            w.write("ok");
        }
        Runtime.getRuntime().exec("cmd /c copy C:\\reports\\leave.csv \\\\fileserver\\share");
    }

    /** 每天凌晨作废超期单据 */
    @Scheduled(cron = "0 30 1 * * ?")
    public void expire() {
        leaveService.expireStale();
    }
}
