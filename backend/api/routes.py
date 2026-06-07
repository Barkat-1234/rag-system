from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import timedelta
import os
import asyncio
import time

# Import your services and database
from backend.services.rag_service import rag_service
from backend.database.db import get_db
from backend.database.models import Document, ChatHistory, User
from backend.auth.auth import create_access_token, verify_password, get_password_hash
from backend.auth.dependencies import get_current_user
from backend.services.cache_service import embedding_cache

# Create router
router = APIRouter()

# Create upload directory
UPLOAD_DIR = "./backend/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============ Pydantic Models ============
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str

# ============ Authentication Endpoints ============

@router.post("/auth/register", response_model=TokenResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if user exists
    existing_user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Create access token
    access_token = create_access_token(data={"sub": str(new_user.id)})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=new_user.id,
        username=new_user.username
    )

@router.post("/auth/login", response_model=TokenResponse)
async def login(login_data: UserLogin, db: Session = Depends(get_db)):
    """Login user and return token"""
    # Find user
    user = db.query(User).filter(User.username == login_data.username).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Verify password
    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        username=user.username
    )

@router.get("/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }

# ============ Document Endpoints (Protected) ============

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a document for RAG processing"""
    try:
        # Check file type
        allowed_extensions = ['.txt', '.pdf']
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"File type not allowed. Allowed: {allowed_extensions}"
            )
        
        # Save file
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Process document with RAG service
        result = rag_service.process_document(file_path, file.filename)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        # Save document metadata to PostgreSQL (linked to user)
        doc_record = Document(
            filename=file.filename,
            file_path=file_path,
            file_size=len(content),
            chunks_created=result.get("chunks_created", 0),
            user_id=current_user.id
        )
        db.add(doc_record)
        db.commit()
        
        # Clear relevant cache after new upload
        embedding_cache.clear()
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "File uploaded and processed successfully",
                "filename": file.filename,
                "size": len(content),
                "chunks_created": result.get("chunks_created", 0),
                "document_id": doc_record.id,
                "status": "indexed"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents")
async def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all uploaded documents for current user"""
    documents = db.query(Document).filter(Document.user_id == current_user.id).all()
    return {
        "documents": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "file_size": doc.file_size,
                "chunks_created": doc.chunks_created,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None
            }
            for doc in documents
        ],
        "count": len(documents)
    }

# ============ Optimized Query Endpoints ============

@router.post("/query")
async def query_document(
    query: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    save_history: bool = True
):
    """Query the RAG system with Gemini (Standard)"""
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is required")
    
    start_time = time.time()
    result = rag_service.query(query)
    elapsed_ms = (time.time() - start_time) * 1000
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    # Save chat history asynchronously
    if save_history:
        asyncio.create_task(save_chat_history_async(
            db, current_user.id, query, result.get("answer", ""), str(result.get("sources", []))
        ))
    
    response = JSONResponse(
        status_code=200,
        content={
            "query": query,
            "answer": result.get("answer", "Processing..."),
            "context": result.get("context", ""),
            "sources": result.get("sources", []),
            "num_chunks": result.get("num_chunks", 0),
            "response_time_ms": round(elapsed_ms, 2)
        }
    )
    response.headers["X-Response-Time-ms"] = str(int(elapsed_ms))
    return response

@router.post("/query/optimized")
async def query_optimized(
    query: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    use_mmr: bool = True,
    save_history: bool = True
):
    """Optimized query with caching and MMR reranking (Faster)"""
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is required")
    
    start_time = time.time()
    
    # Use optimized method with MMR reranking
    result = rag_service.query_optimized(query, use_mmr=use_mmr)
    elapsed_ms = (time.time() - start_time) * 1000
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    # Save chat history asynchronously
    if save_history:
        asyncio.create_task(save_chat_history_async(
            db, current_user.id, query, result.get("answer", ""), str(result.get("sources", []))
        ))
    
    result["response_time_ms"] = round(elapsed_ms, 2)
    
    response = JSONResponse(status_code=200, content=result)
    response.headers["X-Response-Time-ms"] = str(int(elapsed_ms))
    return response

@router.get("/history")
async def get_chat_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 50
):
    """Get recent chat history for current user"""
    history = db.query(ChatHistory).filter(
        ChatHistory.user_id == current_user.id
    ).order_by(ChatHistory.created_at.desc()).limit(limit).all()
    
    return {
        "history": [
            {
                "id": chat.id,
                "question": chat.question,
                "answer": chat.answer[:200] + "..." if len(chat.answer) > 200 else chat.answer,
                "sources": eval(chat.sources) if chat.sources else [],
                "timestamp": chat.created_at.isoformat() if chat.created_at else None
            }
            for chat in history
        ],
        "count": len(history)
    }

@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a document for current user"""
    try:
        # Find document in database (must belong to current user)
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Delete file from disk
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
        
        # Delete from database
        db.delete(document)
        db.commit()
        
        # Clear cache after deletion
        embedding_cache.clear()
        
        return {"message": f"Document '{document.filename}' deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ============ Performance Monitoring Endpoints ============

@router.get("/performance/stats")
async def get_performance_stats():
    """Get cache hit/miss statistics"""
    cache_stats = embedding_cache.get_stats()
    
    return {
        "cache": cache_stats,
        "endpoints": {
            "standard": "/query",
            "optimized": "/query/optimized",
            "performance": "/performance/stats"
        },
        "features": {
            "caching": "Enabled (TTL: 2 hours)",
            "mmr_reranking": "Available",
            "async_history": "Enabled"
        }
    }

@router.get("/performance/cache/clear")
async def clear_cache():
    """Clear the embedding cache"""
    embedding_cache.clear()
    return {"message": "Cache cleared successfully", "status": "success"}

# ============ Helper Functions ============

async def save_chat_history_async(db: Session, user_id: int, question: str, answer: str, sources: str):
    """Background task to save chat history (non-blocking)"""
    try:
        # Create new session for background task
        from backend.database.db import SessionLocal
        new_db = SessionLocal()
        
        chat_record = ChatHistory(
            user_id=user_id,
            question=question,
            answer=answer,
            sources=sources
        )
        new_db.add(chat_record)
        new_db.commit()
        new_db.close()
    except Exception as e:
        print(f"Error saving history async: {e}")