using System.Web.Mvc;
using System.Drawing;
using Erp.Core.Services;

namespace Erp.Web.Controllers
{
    [RoutePrefix("invoice")]
    public class InvoiceController : Controller
    {
        private readonly InvoiceService _svc = new InvoiceService();

        // 发票列表
        [HttpGet]
        [Route("list")]
        public ActionResult List(int page = 1)
        {
            return Json(_svc.List(page), JsonRequestBehavior.AllowGet);
        }

        [HttpPost]
        [Route("submit")]
        public ActionResult Submit(int id)
        {
            _svc.Submit(id);
            return Json(true);
        }

        public ActionResult Stamp(int id)
        {
            using (var bmp = new Bitmap(200, 80))
            {
                var path = Server.MapPath("~/App_Data/stamp.png");
                bmp.Save(path);
            }
            return Content("ok");
        }
    }
}
