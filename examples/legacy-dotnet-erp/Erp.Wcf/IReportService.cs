using System.ServiceModel;

namespace Erp.Wcf
{
    [ServiceContract]
    public interface IReportService
    {
        [OperationContract]
        string MonthlyReport(int month);
    }
}
