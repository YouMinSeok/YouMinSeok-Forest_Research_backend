# app/routers/board.py
from fastapi import APIRouter, HTTPException, Depends, Request
from app.core.database import get_database
from bson import ObjectId
from datetime import datetime, timedelta
import pytz  # 타임존 처리를 위한 라이브러리
from app.utils.security import get_current_user
from pymongo import ReturnDocument

router = APIRouter()

# 서울 타임존 객체 생성
seoul_tz = pytz.timezone('Asia/Seoul')

# ===== 게시글 관련 엔드포인트 =====

@router.post("/create")
async def create_post(post: dict, db=Depends(get_database), user=Depends(get_current_user)):
    if "board" not in post:
        raise HTTPException(status_code=400, detail="게시판 유형(board)이 필요합니다.")
    if "title" not in post or "content" not in post:
        raise HTTPException(status_code=400, detail="제목과 내용은 필수입니다.")

    post["writer"] = user["name"]
    post["writer_id"] = user["id"]
    post["date"] = datetime.now(seoul_tz).isoformat()  # 서울 기준 시간
    post["views"] = 0
    post["likes"] = 0
    post["prefix"] = post.get("prefix", "")

    research_categories = ["연구자료", "제출자료", "제안서"]
    if post["board"] in research_categories:
        post["subcategory"] = post["board"]
        post["board"] = "연구"

    if post["board"] == "연구":
        counter_key = f"{post['subcategory']}_post_number"
    else:
        counter_key = f"{post['board']}_post_number"

    counter = await db["counters"].find_one_and_update(
        {"_id": counter_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    post_number = counter["seq"] if counter else 1
    post["post_number"] = post_number

    collection = db["board"]
    result = await collection.insert_one(post)
    new_post = await collection.find_one({"_id": result.inserted_id})
    if not new_post:
        raise HTTPException(status_code=404, detail="생성된 게시글을 찾을 수 없습니다.")

    new_post["id"] = str(new_post["_id"])
    del new_post["_id"]
    return new_post

@router.get("/")
async def list_posts(category: str = None, db=Depends(get_database)):
    collection = db["board"]
    filter_query = {}
    if category:
        filter_query["board"] = category

    posts_cursor = collection.find(filter_query).sort("post_number", -1)
    posts = await posts_cursor.to_list(50)

    for post in posts:
        post["id"] = str(post["_id"])
        # 댓글 수 동적 계산
        comment_count = await db["comments"].count_documents({"post_id": post["id"]})
        post["commentCount"] = comment_count
        del post["_id"]
    return posts

@router.get("/{post_id}")
async def get_post(post_id: str, db=Depends(get_database)):
    collection = db["board"]
    try:
        oid = ObjectId(post_id)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 post_id입니다.")
    post = await collection.find_one({"_id": oid})
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    post["id"] = str(post["_id"])
    del post["_id"]

    # 댓글 수 동적 계산
    comment_count = await db["comments"].count_documents({"post_id": post_id})
    post["commentCount"] = comment_count

    return post

@router.put("/{post_id}")
async def update_post(post_id: str, update_data: dict, db=Depends(get_database), user=Depends(get_current_user)):
    collection = db["board"]
    try:
        oid = ObjectId(post_id)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 post_id입니다.")
    post = await collection.find_one({"_id": oid})
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    if post.get("writer_id") != user["id"]:
        raise HTTPException(status_code=403, detail="작성자만 수정할 수 있습니다.")

    await collection.update_one({"_id": oid}, {"$set": update_data})
    return {"message": "게시글이 수정되었습니다."}

@router.delete("/{post_id}")
async def delete_post(post_id: str, db=Depends(get_database), user=Depends(get_current_user)):
    collection = db["board"]
    try:
        oid = ObjectId(post_id)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 post_id입니다.")
    post = await collection.find_one({"_id": oid})
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    if post.get("writer_id") != user["id"]:
        raise HTTPException(status_code=403, detail="작성자만 삭제할 수 있습니다.")

    # 게시글과 관련된 데이터들을 함께 삭제
    await collection.delete_one({"_id": oid})

    # 해당 게시글의 모든 댓글 삭제
    comments_collection = db["comments"]
    deleted_comments = await comments_collection.delete_many({"post_id": post_id})

    # 해당 게시글의 모든 좋아요 삭제
    likes_collection = db["post_likes"]
    deleted_likes = await likes_collection.delete_many({"post_id": post_id})

    # 해당 게시글의 모든 조회수 기록 삭제
    views_collection = db["post_views"]
    deleted_views = await views_collection.delete_many({"post_id": post_id})

    # 삭제된 데이터 개수 로그
    print(f"게시글 삭제 완료 - post_id: {post_id}, 댓글: {deleted_comments.deleted_count}개, 좋아요: {deleted_likes.deleted_count}개, 조회수기록: {deleted_views.deleted_count}개")

    return {
        "message": "게시글과 관련 데이터가 모두 삭제되었습니다.",
        "deleted_counts": {
            "comments": deleted_comments.deleted_count,
            "likes": deleted_likes.deleted_count,
            "views": deleted_views.deleted_count
        }
    }

# ===== 조회수 및 좋아요 엔드포인트 =====

VIEW_COOLDOWN = timedelta(minutes=5)

@router.post("/{post_id}/view")
async def increment_view(post_id: str, request: Request, db=Depends(get_database)):
    try:
        oid = ObjectId(post_id)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 post_id입니다.")

    user_id = None
    if hasattr(request.state, "user") and request.state.user:
        user_id = request.state.user.get("id")
    identifier = user_id or request.client.host

    now = datetime.utcnow()  # UTC 기준
    view_collection = db["post_views"]
    view_record = await view_collection.find_one({"post_id": post_id, "identifier": identifier})

    if view_record:
        last_view = view_record.get("last_view")
        if now - last_view < VIEW_COOLDOWN:
            return {"success": False, "reason": "cooldown"}
        else:
            await view_collection.update_one({"_id": view_record["_id"]}, {"$set": {"last_view": now}})
    else:
        await view_collection.insert_one({"post_id": post_id, "identifier": identifier, "last_view": now})

    board_collection = db["board"]
    result = await board_collection.update_one({"_id": oid}, {"$inc": {"views": 1}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    return {"success": True}

@router.post("/{post_id}/like")
async def toggle_like(post_id: str, request: Request, db=Depends(get_database), user=Depends(get_current_user)):
    try:
        oid = ObjectId(post_id)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 post_id입니다.")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="사용자 정보가 올바르지 않습니다.")
    now = datetime.utcnow()

    like_collection = db["post_likes"]
    like_record = await like_collection.find_one({"post_id": post_id, "identifier": user_id})

    board_collection = db["board"]
    if like_record:
        await like_collection.delete_one({"_id": like_record["_id"]})
        await board_collection.update_one({"_id": oid}, {"$inc": {"likes": -1}})
        return {"likeStatus": "unliked"}
    else:
        await like_collection.insert_one({
            "post_id": post_id,
            "identifier": user_id,
            "liked_at": now
        })
        await board_collection.update_one({"_id": oid}, {"$inc": {"likes": 1}})
        return {"likeStatus": "liked"}

# ===== 댓글 관련 엔드포인트 (게시판에 통합) =====

@router.post("/{post_id}/comments/create")
async def create_comment(post_id: str, comment: dict, db=Depends(get_database), user=Depends(get_current_user)):
    """
    댓글/답글 작성 엔드포인트
    - URL 파라미터로 게시글 ID를 받고, 요청 바디에는 'content' (필수) 및 선택적 'image', 'parent_comment_id' 필드를 포함합니다.
    - parent_comment_id가 있으면 답글로 처리됩니다.
    - 로그인한 사용자의 이름과 ID를 댓글 작성자로 기록합니다.
    """
    if "content" not in comment or not comment["content"].strip():
        raise HTTPException(status_code=400, detail="댓글 내용(content)이 필요합니다.")

    # 답글인 경우 부모 댓글 존재 확인
    if "parent_comment_id" in comment and comment["parent_comment_id"]:
        try:
            parent_oid = ObjectId(comment["parent_comment_id"])
            parent_comment = await db["comments"].find_one({"_id": parent_oid, "post_id": post_id})
            if not parent_comment:
                raise HTTPException(status_code=404, detail="부모 댓글을 찾을 수 없습니다.")
        except Exception:
            raise HTTPException(status_code=400, detail="유효하지 않은 parent_comment_id입니다.")

    comment["post_id"] = post_id
    comment["writer"] = user["name"]
    comment["writer_id"] = user["id"]
    comment["date"] = datetime.now(seoul_tz).isoformat()
    comment["parent_comment_id"] = comment.get("parent_comment_id", None)

    result = await db["comments"].insert_one(comment)
    new_comment = await db["comments"].find_one({"_id": result.inserted_id})
    new_comment["id"] = str(new_comment["_id"])
    del new_comment["_id"]
    return new_comment

@router.get("/{post_id}/comments")
async def get_comments(post_id: str, db=Depends(get_database)):
    """
    특정 게시글(post_id)의 댓글 목록을 조회합니다.
    댓글은 작성 시간(date) 기준 오름차순으로 정렬되며, 답글도 함께 반환됩니다.
    """
    comments_cursor = db["comments"].find({"post_id": post_id}).sort("date", 1)
    comments = await comments_cursor.to_list(length=100)

    # 댓글들을 트리 구조로 정리
    comment_dict = {}
    root_comments = []

    for comment in comments:
        comment["id"] = str(comment["_id"])
        del comment["_id"]
        comment["replies"] = []
        comment_dict[comment["id"]] = comment

        # 기존 댓글과의 호환성을 위해 get() 사용
        parent_comment_id = comment.get("parent_comment_id", None)
        if parent_comment_id:
            # 답글인 경우 부모 댓글의 replies에 추가
            if parent_comment_id in comment_dict:
                comment_dict[parent_comment_id]["replies"].append(comment)
        else:
            # 최상위 댓글인 경우
            root_comments.append(comment)

    return root_comments

# ===== 통합 게시판 조회 API =====

@router.get("/all/recent")
async def get_all_recent_posts(limit: int = 50, db=Depends(get_database)):
    """
    모든 게시판의 최근 게시글들을 통합하여 조회합니다.
    각 게시판별로 최신순으로 정렬하여 반환합니다.
    """
    collection = db["board"]

    # 모든 게시글을 최신순으로 조회
    posts_cursor = collection.find({}).sort("date", -1).limit(limit)
    posts = await posts_cursor.to_list(limit)

    for post in posts:
        post["id"] = str(post["_id"])
        del post["_id"]

        # 댓글 수 계산
        comment_count = await db["comments"].count_documents({"post_id": post["id"]})
        post["commentCount"] = comment_count

        # 최근 답글 여부 확인 (최근 3일 내 답글이 있는지)
        recent_reply_count = await db["comments"].count_documents({
            "post_id": post["id"],
            "parent_comment_id": {"$exists": True, "$ne": None},
            "date": {"$gte": (datetime.now(seoul_tz) - timedelta(days=3)).isoformat()}
        })
        post["hasRecentReplies"] = recent_reply_count > 0
        post["recentReplyCount"] = recent_reply_count

    return posts

@router.get("/all/by-category")
async def get_posts_by_category(db=Depends(get_database)):
    """
    카테고리별로 게시글들을 분류하여 반환합니다.
    각 카테고리별로 최신 10개씩 반환합니다.
    """
    collection = db["board"]

    # 카테고리별 게시글 조회
    categories = {
        "자유": "자유",
        "연구자료": "연구",
        "제출자료": "연구",
        "제안서": "연구"
    }

    result = {}

    for category_name, board_type in categories.items():
        if board_type == "연구":
            # 연구 게시판의 경우 subcategory로 필터링
            query = {"board": board_type, "subcategory": category_name}
        else:
            # 자유게시판의 경우
            query = {"board": board_type}

        posts_cursor = collection.find(query).sort("date", -1).limit(10)
        posts = await posts_cursor.to_list(10)

        for post in posts:
            post["id"] = str(post["_id"])
            del post["_id"]

            # 댓글 수 계산
            comment_count = await db["comments"].count_documents({"post_id": post["id"]})
            post["commentCount"] = comment_count

            # 최근 답글 여부 확인
            recent_reply_count = await db["comments"].count_documents({
                "post_id": post["id"],
                "parent_comment_id": {"$exists": True, "$ne": None},
                "date": {"$gte": (datetime.now(seoul_tz) - timedelta(days=3)).isoformat()}
            })
            post["hasRecentReplies"] = recent_reply_count > 0

        result[category_name] = posts

    return result

# ===== 댓글 삭제 엔드포인트 =====

@router.delete("/{post_id}/comments/{comment_id}")
async def delete_comment(post_id: str, comment_id: str, db=Depends(get_database), user=Depends(get_current_user)):
    """
    댓글 삭제 엔드포인트
    - 로그인한 사용자가 작성한 댓글만 삭제할 수 있습니다.
    """
    try:
        comment_oid = ObjectId(comment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 comment_id입니다.")

    comment = await db["comments"].find_one({"_id": comment_oid, "post_id": post_id})
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")

    if comment.get("writer_id") != user["id"]:
        raise HTTPException(status_code=403, detail="작성자만 삭제할 수 있습니다.")

    await db["comments"].delete_one({"_id": comment_oid})
    return {"message": "댓글이 삭제되었습니다."}
