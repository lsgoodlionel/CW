import os
os.environ["DATABASE_URL"]="sqlite:////out/r.db"; os.environ.setdefault("REQUIRE_AUTH","false"); os.environ["UPLOAD_DIR"]="/out/up"
from decimal import Decimal
from datetime import datetime
from app.init_db import init_db
from app.database import SessionLocal
from app import models, approval_doc
from sqlalchemy import select
init_db(); db=SessionLocal()
u=models.OrgUnit(name="综合部"); db.add(u); db.flush()
mgr=models.Employee(name="王经理"); ap=models.Employee(name="小李"); db.add_all([mgr,ap]); db.flush()
acc=db.scalar(select(models.Account).where(models.Account.category=="profit"))
app=models.ExpenseApplication(apply_no="SQ-202608-001",apply_type="contract",reason="年度办公用品合同",
    applicant_employee_id=ap.id,org_unit_id=u.id,estimated_amount=Decimal("5000"),status="approved")
app.items.append(models.ExpenseApplicationItem(category="办公费",account_id=acc.id,sub_account="办公用品",amount=Decimal("5000")))
db.add(app); db.flush()
ia=models.WorkflowInstance(definition_id=1,biz_type="expense_apply",biz_id=app.id,title="申请",status="approved",current_step_no=1); db.add(ia); db.flush()
ia.tasks.append(models.WorkflowTask(instance_id=ia.id,step_no=1,step_name="部门负责人审批",approver_employee_id=mgr.id,result="approved",comment="同意采购",acted_at=datetime(2026,8,1,10,0)))
app.workflow_instance_id=ia.id
claim=models.ExpenseClaim(claim_no="BX-202608-001",applicant_employee_id=ap.id,org_unit_id=u.id,
    application_id=app.id,reason="报销办公用品",total_amount=Decimal("4800"),status="paid")
claim.items.append(models.ExpenseItem(category="办公费",account_id=acc.id,sub_account="办公用品",amount=Decimal("4800")))
db.add(claim); db.flush()
ic=models.WorkflowInstance(definition_id=1,biz_type="expense",biz_id=claim.id,title="报销",status="approved",current_step_no=2); db.add(ic); db.flush()
ic.tasks.append(models.WorkflowTask(instance_id=ic.id,step_no=1,step_name="部门负责人审批",approver_employee_id=mgr.id,result="approved",comment="属实",acted_at=datetime(2026,8,2,9,0)))
ic.tasks.append(models.WorkflowTask(instance_id=ic.id,step_no=2,step_name="财务/管理层审批",approver_employee_id=mgr.id,result="approved",comment="准予报销",acted_at=datetime(2026,8,2,15,0)))
claim.workflow_instance_id=ic.id; db.commit()
pdf=approval_doc.build_claim_approval_pdf(db, claim)
open("/out/sample_approval.pdf","wb").write(pdf)
print("written", len(pdf))
