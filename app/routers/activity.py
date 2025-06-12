# app/routers/activity.py
from fastapi import APIRouter, Depends
from app.core.database import get_database
from datetime import datetime, timedelta
import pytz
from bson import ObjectId

router = APIRouter()

# 서울 타임존 객체 생성
seoul_tz = pytz.timezone('Asia/Seoul')

@router.get("/recent")
async def get_recent_activities(limit: int = 10, db=Depends(get_database)):
    """
    최근 활동 목록을 가져옵니다.
    - 최근 게시글 작성 활동
    - 최근 회원가입 활동
    시간 순으로 정렬하여 통합된 활동 목록을 반환합니다.
    """
    activities = []

    # 최근 30일간의 활동만 조회
    thirty_days_ago = datetime.now(seoul_tz) - timedelta(days=30)

    try:
        # 최근 게시글 작성 활동 조회
        board_collection = db["board"]
        recent_posts_cursor = board_collection.find({
            "date": {"$gte": thirty_days_ago.isoformat()}
        }).sort("date", -1).limit(limit * 2)  # 여유롭게 더 많이 가져와서 나중에 정렬

        recent_posts = await recent_posts_cursor.to_list(length=limit * 2)

        for post in recent_posts:
            # 게시판 이름 처리 - 연구 카테고리의 경우 subcategory 사용
            board_name = post.get("board", "일반")
            if board_name == "연구" and post.get("subcategory"):
                board_name = post.get("subcategory")

            activity = {
                "type": "post",
                "title": post.get("title", "제목 없음"),
                "author": post.get("writer", "익명"),
                "date": post.get("date"),
                "board": board_name,  # 정확한 게시판 이름 사용
                "prefix": post.get("prefix", ""),  # 말머리 정보 추가
                "post_id": str(post["_id"])
            }
            activities.append(activity)

        # 최근 회원가입 활동 조회
        users_collection = db["users"]
        recent_users_cursor = users_collection.find({
            "created_at": {"$gte": thirty_days_ago.replace(tzinfo=None)},  # users는 UTC로 저장됨
            "is_active": True  # 인증 완료된 사용자만
        }).sort("created_at", -1).limit(limit)

        recent_users = await recent_users_cursor.to_list(length=limit)

        for user in recent_users:
            # UTC 시간을 서울 시간으로 변환
            created_at_utc = user.get("created_at")
            if created_at_utc:
                # UTC를 서울 시간으로 변환
                created_at_seoul = created_at_utc.replace(tzinfo=pytz.UTC).astimezone(seoul_tz)
                activity = {
                    "type": "signup",
                    "title": "연구의숲에 가입했습니다",
                    "author": user.get("name", "익명"),
                    "date": created_at_seoul.isoformat(),
                    "role": user.get("role", "")
                }
                activities.append(activity)

        # 날짜순으로 정렬 (최신순)
        activities.sort(key=lambda x: x["date"], reverse=True)

        # 지정된 limit만큼만 반환
        return activities[:limit]

    except Exception as e:
        print(f"Error fetching recent activities: {e}")
        return []

@router.get("/recent-posts")
async def get_recent_posts(limit: int = 10, db=Depends(get_database)):
    """
    최근 게시글 작성 활동만 가져옵니다.
    """
    activities = []
    thirty_days_ago = datetime.now(seoul_tz) - timedelta(days=30)

    try:
        # 최근 게시글 작성 활동만 조회
        board_collection = db["board"]
        recent_posts_cursor = board_collection.find({
            "date": {"$gte": thirty_days_ago.isoformat()}
        }).sort("date", -1).limit(limit)

        recent_posts = await recent_posts_cursor.to_list(length=limit)

        for post in recent_posts:
            # 게시판 이름 처리 - 연구 카테고리의 경우 subcategory 사용
            board_name = post.get("board", "일반")
            if board_name == "연구" and post.get("subcategory"):
                board_name = post.get("subcategory")

            activity = {
                "type": "post",
                "title": post.get("title", "제목 없음"),
                "author": post.get("writer", "익명"),
                "date": post.get("date"),
                "board": board_name,  # 정확한 게시판 이름 사용
                "prefix": post.get("prefix", ""),  # 말머리 정보 추가
                "post_id": str(post["_id"])
            }
            activities.append(activity)

        return activities

    except Exception as e:
        print(f"Error fetching recent posts: {e}")
        return []

@router.get("/recent-comments")
async def get_recent_comments(limit: int = 10, db=Depends(get_database)):
    """
    최근 댓글 작성 활동을 가져옵니다.
    """
    activities = []
    thirty_days_ago = datetime.now(seoul_tz) - timedelta(days=30)

    try:
        # 최근 댓글 작성 활동 조회 - post_id별로 그룹화하여 가장 최근 댓글만 가져오기
        comments_collection = db["comments"]

        # MongoDB aggregation을 사용하여 post_id별로 그룹화하고 가장 최근 댓글만 선택
        pipeline = [
            {
                "$match": {
                    "date": {"$gte": thirty_days_ago.isoformat()}
                }
            },
            {
                "$sort": {"date": -1}
            },
            {
                "$group": {
                    "_id": "$post_id",  # post_id별로 그룹화
                    "latest_comment": {"$first": "$$ROOT"}  # 각 그룹에서 가장 최근 댓글만 선택
                }
            },
            {
                "$match": {
                    "latest_comment": {"$ne": None}  # null 값 필터링
                }
            },
            {
                "$replaceRoot": {"newRoot": "$latest_comment"}  # 결과를 원래 댓글 구조로 변환
            },
            {
                "$sort": {"date": -1}  # 다시 날짜순으로 정렬
            },
            {
                "$limit": limit
            }
        ]

        recent_comments_cursor = comments_collection.aggregate(pipeline)
        recent_comments = await recent_comments_cursor.to_list(length=limit)

        for comment in recent_comments:
            # 해당 댓글의 게시글 정보 조회
            board_collection = db["board"]
            try:
                post_id = ObjectId(comment.get("post_id"))
                post = await board_collection.find_one({"_id": post_id})
                post_title = post.get("title", "제목 없음") if post else "게시글 없음"

                # 게시판 이름 처리 - 연구 카테고리의 경우 subcategory 사용
                if post:
                    board_name = post.get("board", "일반")
                    if board_name == "연구" and post.get("subcategory"):
                        board_name = post.get("subcategory")
                    prefix = post.get("prefix", "")
                else:
                    board_name = "일반"
                    prefix = ""
            except:
                post_title = "게시글 없음"
                board_name = "일반"
                prefix = ""

            # 댓글 내용 처리 (가독성을 위해 60자로 제한)
            comment_content = comment.get("content", "").strip()
            content_preview = comment_content[:60] + "..." if len(comment_content) > 60 else comment_content

            activity = {
                "type": "comment",
                "title": post_title,  # 게시글 제목만 표시
                "author": comment.get("writer", "익명"),
                "date": comment.get("date"),
                "board": board_name,
                "prefix": prefix,  # 말머리 정보 추가
                "post_id": comment.get("post_id"),
                "comment_id": str(comment["_id"]),
                "content": content_preview,
                "parent_comment_id": comment.get("parent_comment_id")  # 답글 여부 판단을 위해 추가
            }
            activities.append(activity)

        return activities

    except Exception as e:
        print(f"Error fetching recent comments: {e}")
        return []

@router.get("/recent-signups")
async def get_recent_signups(limit: int = 10, db=Depends(get_database)):
    """
    최근 회원가입 활동만 가져옵니다.
    """
    activities = []
    thirty_days_ago = datetime.now(seoul_tz) - timedelta(days=30)

    try:
        # 최근 회원가입 활동 조회
        users_collection = db["users"]
        recent_users_cursor = users_collection.find({
            "created_at": {"$gte": thirty_days_ago.replace(tzinfo=None)},  # users는 UTC로 저장됨
            "is_active": True  # 인증 완료된 사용자만
        }).sort("created_at", -1).limit(limit)

        recent_users = await recent_users_cursor.to_list(length=limit)

        for user in recent_users:
            # UTC 시간을 서울 시간으로 변환
            created_at_utc = user.get("created_at")
            if created_at_utc:
                # UTC를 서울 시간으로 변환
                created_at_seoul = created_at_utc.replace(tzinfo=pytz.UTC).astimezone(seoul_tz)
                activity = {
                    "type": "signup",
                    "title": "연구의숲에 가입했습니다",
                    "author": user.get("name", "익명"),
                    "date": created_at_seoul.isoformat(),
                    "role": user.get("role", "")
                }
                activities.append(activity)

        return activities

    except Exception as e:
        print(f"Error fetching recent signups: {e}")
        return []
