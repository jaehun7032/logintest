from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from flask_pymongo import PyMongo
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from bson import ObjectId
from dotenv import load_dotenv
from datetime import datetime
import logging
import os

# 환경변수 로드
load_dotenv()

app = Flask(__name__)
app.config["MONGO_URI"] = f"mongodb://{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
app.secret_key = os.getenv('SECRET_KEY')

mongo = PyMongo(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)

# --- 유저 클래스 (UserMixin만 활용) ---
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.username = user_data["username"]
        self.invitations = user_data.get("invitations", [])

    def get_id(self):
        return self.id

# --- 유저 로드 함수 ---
@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    return User(user_data) if user_data else None

# 홈 페이지 라우트 추가
@app.route('/')
def home():
    return render_template("home.html")  # home.html 파일을 추가해야 합니다

# 로그인, 로그아웃, 회원가입 등 기존 라우트...

# favicon 처리 라우트 추가
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico')

# 대시보드
@app.route('/dashboard')
@login_required
def dashboard():
    user_data = mongo.db.users.find_one({"_id": ObjectId(current_user.id)})
    projects = mongo.db.projects.find({"members": ObjectId(current_user.id)})

    project_list = []
    for project in projects:
        if "owner" in project:
            project["owner"] = str(project["owner"])
        else:
            project["owner"] = None

        project_list.append(project)

    return render_template(
        "dashboard.html",
        user={"_id": str(current_user.id), "username": current_user.username},
        projects=project_list
    )

# 프로젝트 생성 라우트 수정...
# 태스크 관련 라우트 수정...

# 에러 처리 라우트 추가 (예외 발생 시, 사용자에게 명확한 메시지 제공)
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({"error": "페이지를 찾을 수 없습니다."}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "서버 오류가 발생했습니다. 나중에 다시 시도해주세요."}), 500

if __name__ == "__main__":
    app.run(debug=True)

