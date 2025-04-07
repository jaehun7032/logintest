from flask import Flask, render_template, request, jsonify, redirect, url_for, session
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

# 회원가입
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        if mongo.db.users.find_one({"username": username}):
            return "이미 존재하는 사용자입니다."

        mongo.db.users.insert_one({
            "username": username,
            "password": hashed_password,
            "invitations": []
        })
        return redirect(url_for("login"))

    return render_template("register.html")

# 로그인
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user_data = mongo.db.users.find_one({"username": username})

        if user_data and bcrypt.check_password_hash(user_data["password"], password):
            user = User(user_data)
            login_user(user)
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        else:
            return "로그인 실패! 아이디 또는 비밀번호를 확인하세요."

    return render_template("login.html")

# 로그아웃
@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("user_id", None)
    return redirect(url_for("login"))

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

# 프로젝트 생성
@app.route("/projects/create", methods=["POST"])
@login_required
def create_project():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"message": "프로젝트 이름이 필요합니다."}), 400

    try:
        new_project = {
            "name": data["name"],
            "description": data.get("description", ""),
            "members": [ObjectId(current_user.id)],
            "owner": ObjectId(current_user.id),  # 👈 생성자 ID 추가
            "created_at": datetime.utcnow()
        }

        result = mongo.db.projects.insert_one(new_project)
        logging.debug(f"삽입 결과: {result.inserted_id}")

        return jsonify({
            "id": str(result.inserted_id),
            "name": new_project["name"]
        }), 201
    except Exception as e:
        logging.exception("프로젝트 저장 중 오류 발생")
        return jsonify({"message": "서버 오류"}), 500

# 프로젝트 삭제
@app.route("/projects/<project_id>", methods=["DELETE"])
@login_required
def delete_or_leave_project(project_id):
    project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        return jsonify({"error": "Project not found"}), 404

    user_id = ObjectId(current_user.id)

    # 🔥 사용자가 owner면 프로젝트 자체를 삭제
    if project.get("owner") == user_id:
        mongo.db.projects.delete_one({"_id": ObjectId(project_id)})
        return jsonify({"message": "Project deleted"}), 200

    # 🔥 멤버이면 탈퇴 처리
    elif user_id in project.get("members", []):
        mongo.db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {"$pull": {"members": user_id}}
        )
        return jsonify({"message": "Left project"}), 200

    # 🔥 아무 관련 없는 사람
    return jsonify({"error": "Unauthorized"}), 403

# 프로젝트 조회
@app.route("/projects/<project_id>", methods=["GET"])
@login_required
def get_project(project_id):
    project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
    if project:
        return jsonify({"id": str(project["_id"]), "name": project["name"]}), 200
    return jsonify({"message": "Project not found"}), 404

# 초대
@app.route('/projects/<project_id>/invite', methods=['POST'])
@login_required
def invite_member(project_id):
    data = request.get_json()
    username = data.get('username')

    user = mongo.db.users.find_one({"username": username})
    project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})

    if not user or not project:
        return jsonify({"message": "사용자 또는 프로젝트를 찾을 수 없습니다."}), 404

    if ObjectId(user["_id"]) in project.get("members", []):
        return jsonify({"message": "이미 프로젝트 멤버입니다."}), 400

    if ObjectId(project["_id"]) in user.get("invitations", []):
        return jsonify({"message": "이미 초대된 사용자입니다."}), 400

    mongo.db.users.update_one(
        {"_id": user["_id"]},
        {"$push": {"invitations": project["_id"]}}
    )
    return jsonify({"message": "초대가 전송되었습니다."}), 200


@app.route('/invitations', methods=['GET'])
@login_required
def get_invitations():
    user_data = mongo.db.users.find_one({"_id": ObjectId(current_user.id)})
    invitations = list(mongo.db.projects.find({"_id": {"$in": user_data.get("invitations", [])}}))
    return jsonify({
        "invitations": [{"id": str(p["_id"]), "name": p["name"]} for p in invitations]
    })

@app.route('/invitations/respond', methods=['POST'])
@login_required
def respond_invitation():
    data = request.get_json()
    project_id = ObjectId(data.get("project_id"))
    action = data.get("action")

    mongo.db.users.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$pull": {"invitations": project_id}}
    )

    if action == "accept":
        mongo.db.projects.update_one(
            {"_id": project_id},
            {"$addToSet": {"members": ObjectId(current_user.id)}}
        )

    return jsonify({"message": f"{action} 처리 완료"}), 200

# 태스크 추가
@app.route("/add", methods=["POST"])
@login_required
def add_task():
    data = request.json
    mongo.db.tasks.insert_one(data)
    return jsonify({"message": "Task added"}), 201

# 태스크 수정
@app.route("/update/<task_id>", methods=["PUT"])
@login_required
def update_task(task_id):
    data = request.json
    mongo.db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": data["status"]}}
    )
    return jsonify({"message": "Task updated"}), 200

# 태스크 삭제
@app.route("/delete/<task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    mongo.db.tasks.delete_one({"_id": ObjectId(task_id)})
    return jsonify({"message": "Task deleted"}), 200

if __name__ == "__main__":
    app.run(debug=True)
