using System;
using System.Collections.Generic;
using System.Configuration;
using System.Data.SqlClient;
using Microsoft.Win32;
using System.Security.Cryptography;
using System.Text;

namespace Erp.Core.Services
{
    public class InvoiceService
    {
        public List<string> List(int page)
        {
            var result = new List<string>();
            var cs = ConfigurationManager.ConnectionStrings["Erp"].ConnectionString;
            using (var conn = new SqlConnection(cs))
            {
                conn.Open();
                var cmd = new SqlCommand("SELECT TOP 20 InvoiceNo, ISNULL(Title,'') FROM dbo.Invoice WITH (NOLOCK) WHERE CreatedAt > DATEADD(day,-30,GETDATE())", conn);
                using (var r = cmd.ExecuteReader()) { while (r.Read()) result.Add(r.GetString(0)); }
            }
            return result;
        }

        // 提交发票：只有草稿状态可以提交
        public void Submit(int id)
        {
            var cs = ConfigurationManager.ConnectionStrings["Erp"].ConnectionString;
            using (var conn = new SqlConnection(cs))
            {
                conn.Open();
                var cmd = new SqlCommand("UPDATE dbo.Invoice SET Status = 'Submitted', SubmittedAt = GETDATE() WHERE Id = @id AND Status = 'Draft'", conn);
                cmd.Parameters.AddWithValue("@id", id);
                if (cmd.ExecuteNonQuery() == 0) throw new InvalidOperationException("只有草稿可以提交");
            }
        }

        public string LicensePath()
        {
            return (string)Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Acme\Erp").GetValue("LicensePath");
        }

        public string Sign(string data)
        {
            using (var rsa = new RSACryptoServiceProvider())
            {
                return Convert.ToBase64String(rsa.SignData(Encoding.Default.GetBytes(data), "SHA1"));
            }
        }
    }
}
