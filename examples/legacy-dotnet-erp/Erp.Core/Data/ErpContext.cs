using System.Data.Entity;

namespace Erp.Core.Data
{
    public class ErpContext : DbContext
    {
        public DbSet<Customer> Customers { get; set; }
    }

    [System.ComponentModel.DataAnnotations.Schema.Table("Customer")]
    public class Customer { public int Id { get; set; } public string Name { get; set; } }
}
