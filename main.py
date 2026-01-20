import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# --- 1. 数据库配置 (SQLite) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./safecheck.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- 2. 数据模型 (Models) ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    phone = Column(String)
    last_checkin = Column(DateTime, default=datetime.datetime.now)
    status = Column(String, default="safe")  # safe, warning_2, warning_3, sos


class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    phone = Column(String)
    relation = Column(String)


class CheckinLog(Base):
    __tablename__ = "checkin_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    checkin_time = Column(DateTime, default=datetime.datetime.now)
    checkin_type = Column(String)  # auto, manual


Base.metadata.create_all(bind=engine)


# --- 3. Pydantic Schemas (用于API交互) ---
class ContactCreate(BaseModel):
    name: str
    phone: str
    relation: str


class UserStatus(BaseModel):
    status: str
    last_checkin_str: str
    days_since_checkin: int
    checkin_logs: List[datetime.datetime]


# --- 4. FastAPI 应用 ---
app = FastAPI(title="死了么 App API", version="1.0")

# 配置跨域，允许前端直接调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- 5. 核心业务逻辑 ---

# 模拟当前用户ID (MVP固定为1)
CURRENT_USER_ID = 1


@app.on_event("startup")
def startup_db_data():
    """初始化测试数据"""
    db = SessionLocal()
    if not db.query(User).filter(User.id == CURRENT_USER_ID).first():
        user = User(id=CURRENT_USER_ID, username="dev_user", phone="13800138000")
        db.add(user)
        # 添加一些历史签到记录
        for i in range(1, 4):
            past_date = datetime.datetime.now() - datetime.timedelta(days=i)
            db.add(CheckinLog(user_id=CURRENT_USER_ID, checkin_time=past_date, checkin_type="auto"))
        db.commit()
    db.close()


def calculate_status(last_checkin: datetime.datetime):
    """根据最后签到时间计算状态"""
    if not last_checkin:
        return "safe", 0

    delta = datetime.datetime.now() - last_checkin
    days = delta.days

    if days < 2:
        return "safe", days
    elif days < 3:
        return "warning_2", days
    elif days < 5:
        return "warning_3", days
    else:
        return "sos", days


# --- API 接口 ---

@app.get("/api/status")
def get_status(db: Session = Depends(get_db)):
    """首页获取核心状态"""
    user = db.query(User).filter(User.id == CURRENT_USER_ID).first()
    status_code, days = calculate_status(user.last_checkin)

    # 获取最近7天记录
    logs = db.query(CheckinLog).filter(CheckinLog.user_id == CURRENT_USER_ID).order_by(
        CheckinLog.checkin_time.desc()).limit(7).all()
    log_dates = [log.checkin_time for log in logs]

    return {
        "status": status_code,  # safe, warning_2, warning_3, sos
        "last_checkin_time": user.last_checkin.strftime("%Y-%m-%d %H:%M:%S"),
        "days_since": days,
        "recent_logs": log_dates
    }


@app.post("/api/checkin")
def checkin(type: str = "manual", db: Session = Depends(get_db)):
    """签到接口 (支持自动/手动)"""
    user = db.query(User).filter(User.id == CURRENT_USER_ID).first()
    now = datetime.datetime.now()

    user.last_checkin = now
    user.status = "safe"  # 重置状态

    log = CheckinLog(user_id=CURRENT_USER_ID, checkin_time=now, checkin_type=type)
    db.add(log)
    db.commit()

    return {"message": "Checkin successful", "time": now}


@app.post("/api/sos")
def trigger_sos(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """触发SOS"""
    # 在后台发送短信/电话 (模拟)
    background_tasks.add_task(mock_send_sms_and_call)
    return {"message": "SOS triggered", "status": "sent"}


def mock_send_sms_and_call():
    print("【模拟后台任务】正在发送短信给紧急联系人...")
    print("【模拟后台任务】正在拨打电话...")
    # 这里可以对接阿里云短信/Twilio API


@app.get("/api/contacts")
def get_contacts(db: Session = Depends(get_db)):
    return db.query(Contact).filter(Contact.user_id == CURRENT_USER_ID).all()


@app.post("/api/contacts")
def add_contact(contact: ContactCreate, db: Session = Depends(get_db)):
    new_contact = Contact(user_id=CURRENT_USER_ID, **contact.dict())
    db.add(new_contact)
    db.commit()
    return new_contact


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
