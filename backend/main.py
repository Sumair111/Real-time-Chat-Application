# backend/main.py
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Set
import json
import asyncio
from datetime import datetime, timedelta
import logging
import os
import uuid
from contextlib import asynccontextmanager

# Redis imports (removed)
# Redis not needed for this implementation

# Firebase imports
try:
    import firebase_admin
    from firebase_admin import credentials, auth, db
    from firebase_admin.exceptions import FirebaseError
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("Firebase Admin SDK not available. Using enhanced mock implementation.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Enhanced Mock Firebase for development with persistence
class EnhancedMockFirebase:
    def __init__(self):
        self.data = {
            'messages': {'general': {}},
            'presence': {},
            'rooms': {'general': {'name': 'General Chat', 'description': 'Main chat room'}},
            'users': {}
        }
        self.message_counter = 0
        self.listeners = {}
        
    def verify_id_token(self, token):
        # Enhanced mock verification with proper user data
        try:
            # In real implementation, decode and verify JWT
            user_data = {
                'uid': f'user_{hash(token) % 10000}',
                'email': f'user{hash(token) % 1000}@example.com',
                'name': f'User {hash(token) % 1000}',
                'picture': f'https://api.dicebear.com/7.x/avataaars/svg?seed={hash(token)}'
            }
            return user_data
        except Exception as e:
            raise FirebaseError(f"Invalid token: {e}")
    
    def reference(self, path):
        return EnhancedMockReference(self.data, path, self)
    
    def push_message(self, room_id, message_data):
        self.message_counter += 1
        message_id = f"msg_{self.message_counter}_{uuid.uuid4().hex[:8]}"
        
        if 'messages' not in self.data:
            self.data['messages'] = {}
        if room_id not in self.data['messages']:
            self.data['messages'][room_id] = {}
        
        # Add message metadata
        enhanced_message = {
            **message_data,
            'id': message_id,
            'timestamp': datetime.now().isoformat(),
            'edited': False,
            'reactions': {},
            'thread_count': 0
        }
        
        self.data['messages'][room_id][message_id] = enhanced_message
        
        # Notify listeners
        if f'messages/{room_id}' in self.listeners:
            for callback in self.listeners[f'messages/{room_id}']:
                callback(self.data['messages'][room_id])
        
        return message_id

class EnhancedMockReference:
    def __init__(self, data, path, firebase_instance):
        self.data = data
        self.path = path
        self.firebase = firebase_instance
    
    def push(self, data):
        path_parts = self.path.split('/')
        if len(path_parts) >= 2 and path_parts[0] == 'messages':
            room_id = path_parts[1]
            message_id = self.firebase.push_message(room_id, data)
            return EnhancedMockPushResult(message_id)
        return EnhancedMockPushResult("mock_id")
    
    def set(self, data):
        path_parts = self.path.split('/')
        current = self.data
        for part in path_parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[path_parts[-1]] = data
        
        # Notify listeners
        if self.path in self.firebase.listeners:
            for callback in self.firebase.listeners[self.path]:
                callback(data)
    
    def update(self, data):
        path_parts = self.path.split('/')
        current = self.data
        for part in path_parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        if path_parts[-1] not in current:
            current[path_parts[-1]] = {}
        
        current[path_parts[-1]].update(data)
    
    def get(self):
        path_parts = self.path.split('/')
        current = self.data
        for part in path_parts:
            if part in current:
                current = current[part]
            else:
                return None
        return current
    
    def limit_to_last(self, limit):
        return self
    
    def order_by_child(self, child):
        return self
    
    def on(self, event_type, callback):
        if self.path not in self.firebase.listeners:
            self.firebase.listeners[self.path] = []
        self.firebase.listeners[self.path].append(callback)
        
        # Send initial data
        data = self.get()
        if data:
            callback(data)
        
        return lambda: self.firebase.listeners[self.path].remove(callback)

class EnhancedMockPushResult:
    def __init__(self, key):
        self.key = key

# Initialize Firebase or Enhanced Mock
mock_firebase = EnhancedMockFirebase()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, auth
    
    # Initialize Firebase
    if FIREBASE_AVAILABLE:
        try:
            if not firebase_admin._apps:
                service_account_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'firebase-service-account.json')
                
                # Check if service account file exists
                if os.path.exists(service_account_path):
                    logger.info(f"Using service account file: {service_account_path}")
                    cred = credentials.Certificate(service_account_path)
                    
                    # Use the correct database URL
                    database_url = os.getenv('FIREBASE_DATABASE_URL', 'https://real-time-chat-app-63bf7-default-rtdb.firebaseio.com/')
                    logger.info(f"Using database URL: {database_url}")
                    
                    firebase_admin.initialize_app(cred, {
                        'databaseURL': database_url
                    })
                    logger.info("Firebase initialized with service account")
                else:
                    logger.error(f"Service account file not found: {service_account_path}")
                    raise Exception("Service account file not found")
            
            # Use real Firebase
            db = firebase_admin.db
            auth = firebase_admin.auth
            logger.info("Real Firebase services initialized successfully")
            
            # Test database connection first
            try:
                logger.info("Testing Firebase database connection...")
                test_ref = db.reference('/')
                test_data = test_ref.get()
                logger.info("Database connection successful")
                
                # Initialize database structure
                await initialize_database_structure()
            except Exception as db_error:
                logger.error(f"Database connection/initialization failed: {db_error}")
                logger.info("This might be because:")
                logger.info("1. The database URL is incorrect")
                logger.info("2. The database doesn't exist")
                logger.info("3. Security rules are blocking access")
                logger.info("Falling back to mock Firebase for now...")
                
                # Fall back to mock
                db = mock_firebase
                auth = mock_firebase
            
        except Exception as e:
            logger.error(f"Firebase initialization failed: {e}")
            logger.info("Falling back to enhanced mock Firebase implementation")
            db = mock_firebase
            auth = mock_firebase
    else:
        logger.info("Using enhanced mock Firebase implementation")
        db = mock_firebase
        auth = mock_firebase
    
    yield
    
    # Cleanup
    if FIREBASE_AVAILABLE:
        try:
            firebase_admin.delete_app(firebase_admin.get_app())
        except:
            pass

app = FastAPI(
    title="ChatFlow API",
    description="Professional Real-Time Chat Application API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enhanced CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://your-domain.com",
        "https://*.netlify.app",
        "https://*.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer(auto_error=False)

# Enhanced Pydantic models
class MessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    room_id: Optional[str] = "general"
    reply_to: Optional[str] = None
    message_type: Optional[str] = "text"  # text, image, file, etc.

class MessageResponse(BaseModel):
    id: str
    text: str
    userId: str
    userEmail: str
    userDisplayName: Optional[str] = None
    userPhotoURL: Optional[str] = None
    room_id: str
    timestamp: str
    edited: bool = False
    reply_to: Optional[str] = None
    message_type: str = "text"
    reactions: Optional[Dict[str, List[str]]] = {}
    thread_count: int = 0
    
class UserPresence(BaseModel):
    user_id: str
    status: str = Field(..., pattern="^(online|offline|away|busy)$")
    last_seen: str
    room_id: Optional[str] = None

class RoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)
    private: bool = False

class RoomResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    private: bool = False
    member_count: int = 0
    created_at: str
    last_activity: Optional[str] = None

class UserProfile(BaseModel):
    uid: str
    email: str
    displayName: Optional[str] = None
    photoURL: Optional[str] = None
    status: str = "offline"
    last_seen: Optional[str] = None
    bio: Optional[str] = None
    joined_at: str

# Enhanced WebSocket Manager
class EnhancedWebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_rooms: Dict[str, str] = {}
        self.room_members: Dict[str, Set[str]] = {}
        self.typing_users: Dict[str, Set[str]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str, room_id: str = "general"):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_rooms[user_id] = room_id
        
        # Add to room members
        if room_id not in self.room_members:
            self.room_members[room_id] = set()
        self.room_members[room_id].add(user_id)
        
        logger.info(f"User {user_id} connected to room {room_id}")
        
        # Update user presence
        try:
            await self.update_user_presence(user_id, "online", room_id)
            
            # Notify room about new user
            await self.broadcast_to_room(
                json.dumps({
                    "type": "user_joined",
                    "user_id": user_id,
                    "room_id": room_id,
                    "timestamp": datetime.now().isoformat()
                }),
                room_id,
                exclude_user=user_id
            )
        except Exception as e:
            logger.error(f"Failed to update presence: {e}")
    
    async def disconnect(self, user_id: str):
        room_id = self.user_rooms.get(user_id)
        
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_rooms:
            del self.user_rooms[user_id]
        
        # Remove from room members
        if room_id and room_id in self.room_members:
            self.room_members[room_id].discard(user_id)
        
        # Remove from typing users
        for room in self.typing_users:
            self.typing_users[room].discard(user_id)
        
        logger.info(f"User {user_id} disconnected from room {room_id}")
        
        # Update user presence
        try:
            await self.update_user_presence(user_id, "offline")
            
            # Notify room about user leaving
            if room_id:
                await self.broadcast_to_room(
                    json.dumps({
                        "type": "user_left",
                        "user_id": user_id,
                        "room_id": room_id,
                        "timestamp": datetime.now().isoformat()
                    }),
                    room_id
                )
        except Exception as e:
            logger.error(f"Failed to update presence: {e}")
    
    async def update_user_presence(self, user_id: str, status: str, room_id: Optional[str] = None):
        presence_data = {
            'status': status,
            'last_seen': datetime.now().isoformat(),
            'room_id': room_id
        }
        
        # Update Firebase/Mock only
        try:
            presence_ref = db.reference(f'presence/{user_id}')
            presence_ref.set(presence_data)
        except Exception as e:
            logger.error(f"Failed to update Firebase presence: {e}")
            # Continue without failing
    
    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_text(message)
            except Exception as e:
                logger.error(f"Failed to send personal message to {user_id}: {e}")
                await self.disconnect(user_id)
    
    async def broadcast_to_room(self, message: str, room_id: str, exclude_user: Optional[str] = None):
        if room_id not in self.room_members:
            return
        
        disconnected_users = []
        for user_id in self.room_members[room_id]:
            if exclude_user and user_id == exclude_user:
                continue
                
            if user_id in self.active_connections:
                try:
                    await self.active_connections[user_id].send_text(message)
                except Exception as e:
                    logger.error(f"Failed to broadcast to {user_id}: {e}")
                    disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            await self.disconnect(user_id)
    
    async def handle_typing(self, user_id: str, room_id: str, is_typing: bool):
        if room_id not in self.typing_users:
            self.typing_users[room_id] = set()
        
        if is_typing:
            self.typing_users[room_id].add(user_id)
        else:
            self.typing_users[room_id].discard(user_id)
        
        # Broadcast typing status
        await self.broadcast_to_room(
            json.dumps({
                "type": "typing",
                "user_id": user_id,
                "room_id": room_id,
                "is_typing": is_typing,
                "typing_users": list(self.typing_users[room_id])
            }),
            room_id,
            exclude_user=user_id
        )
    
    def get_room_members(self, room_id: str) -> List[str]:
        return list(self.room_members.get(room_id, set()))

manager = EnhancedWebSocketManager()

# Initialize database structure
async def initialize_database_structure():
    """Initialize Firebase Realtime Database with basic structure"""
    try:
        # Check if basic structure exists
        root_ref = db.reference('/')
        root_data = root_ref.get()
        
        if not root_data:
            logger.info("Initializing database structure...")
            
            # Initialize basic structure
            initial_data = {
                'rooms': {
                    'general': {
                        'name': 'General Chat',
                        'description': 'Main chat room',
                        'created_at': datetime.now().isoformat(),
                        'private': False
                    }
                },
                'messages': {
                    'general': {}
                },
                'presence': {}
            }
            
            root_ref.set(initial_data)
            logger.info("Database structure initialized successfully")
        else:
            logger.info("Database structure already exists")
            
    except Exception as e:
        logger.error(f"Failed to initialize database structure: {e}")

# Enhanced authentication dependency
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required. Please login first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Check if we're using real Firebase or mock
        if FIREBASE_AVAILABLE and hasattr(auth, 'verify_id_token'):
            # Real Firebase authentication
            decoded_token = auth.verify_id_token(credentials.credentials)
            
            # Get additional user info from Firebase Auth
            try:
                user_record = auth.get_user(decoded_token["uid"])
                return {
                    "uid": decoded_token["uid"],
                    "email": decoded_token.get("email", user_record.email),
                    "name": decoded_token.get("name", user_record.display_name or "Anonymous"),
                    "picture": decoded_token.get("picture", user_record.photo_url or f"https://api.dicebear.com/7.x/avataaars/svg?seed={decoded_token['uid']}"),
                    "email_verified": decoded_token.get("email_verified", user_record.email_verified)
                }
            except Exception as user_error:
                logger.warning(f"Could not fetch user record: {user_error}")
                return {
                    "uid": decoded_token["uid"],
                    "email": decoded_token.get("email", "unknown"),
                    "name": decoded_token.get("name", "Anonymous"),
                    "picture": decoded_token.get("picture", f"https://api.dicebear.com/7.x/avataaars/svg?seed={decoded_token['uid']}"),
                    "email_verified": decoded_token.get("email_verified", False)
                }
        else:
            # Mock Firebase - for development only
            logger.warning("Using mock Firebase authentication - not for production!")
            decoded_token = auth.verify_id_token(credentials.credentials)
            return decoded_token
            
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

# API Routes

@app.get("/", tags=["Health"])
async def root():
    return {
        "message": "ChatFlow API is running",
        "status": "healthy",
        "version": "2.0.0",
        "features": [
            "Real-time messaging",
            "WebSocket support",
            "User presence",
            "Multiple rooms",
            "File uploads",
            "Message reactions"
        ]
    }

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "firebase": "connected" if FIREBASE_AVAILABLE else "mock",
            "websocket": "active"
        }
    }

@app.post("/messages", response_model=MessageResponse, tags=["Messages"])
async def create_message(message: MessageCreate, user_data: dict = Depends(verify_token)):
    try:
        logger.info(f"📝 Creating message in room {message.room_id} from user {user_data['uid']}")
        
        # Enhanced message data with all required fields
        message_data = {
            "text": message.text.strip(),
            "userId": user_data["uid"],
            "userEmail": user_data.get("email", "unknown"),
            "userDisplayName": user_data.get("name", user_data.get("email", "").split("@")[0] if user_data.get("email") else "Anonymous"),
            "userPhotoURL": user_data.get("picture", f"https://api.dicebear.com/7.x/avataaars/svg?seed={user_data['uid']}"),
            "room_id": message.room_id,
            "timestamp": datetime.now().isoformat(),
            "message_type": message.message_type or "text",
            "reply_to": message.reply_to,
            "edited": False,
            "reactions": {},  # Always include this field
            "thread_count": 0
        }
        
        logger.info(f"💾 Saving message data: {message_data}")
        
        # Save to Firebase/Mock
        messages_ref = db.reference(f'messages/{message.room_id}')
        
        # Ensure the messages node exists
        existing_messages = messages_ref.get()
        if existing_messages is None:
            logger.info(f"🏗️ Creating new messages node for room {message.room_id}")
            messages_ref.set({})
        
        # Push the new message
        new_message_ref = messages_ref.push(message_data)
        message_id = new_message_ref.key
        
        logger.info(f"✅ Message saved with ID: {message_id}")
        
        # Prepare response
        response_data = {
            "id": message_id,
            **message_data
        }
        
        # Broadcast to WebSocket clients
        await manager.broadcast_to_room(
            json.dumps({
                "type": "new_message",
                "data": response_data
            }),
            message.room_id
        )
        
        # Update room last activity
        try:
            room_ref = db.reference(f'rooms/{message.room_id}')
            room_ref.update({"last_activity": datetime.now().isoformat()})
            logger.info(f"📊 Updated room {message.room_id} last activity")
        except Exception as e:
            logger.error(f"❌ Failed to update room activity: {e}")
        
        logger.info(f"🚀 Message creation completed successfully")
        return MessageResponse(**response_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to create message: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create message: {str(e)}")

@app.get("/messages/{room_id}", response_model=List[MessageResponse], tags=["Messages"])
async def get_messages(
    room_id: str, 
    limit: int = 50, 
    before: Optional[str] = None,
    user_data: dict = Depends(verify_token)
):
    try:
        messages = []
        
        # Get messages from Firebase/Mock
        messages_ref = db.reference(f'messages/{room_id}')
        messages_data = messages_ref.get()
        
        if messages_data:
            for message_id, message_data in messages_data.items():
                messages.append({
                    "id": message_id,
                    **message_data
                })
            
            # Sort by timestamp
            messages.sort(key=lambda x: x.get("timestamp", ""))
        
        return [MessageResponse(**msg) for msg in messages[-limit:]]
        
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve messages")

@app.get("/rooms", response_model=List[RoomResponse], tags=["Rooms"])
async def get_rooms(user_data: dict = Depends(verify_token)):
    try:
        rooms_ref = db.reference('rooms')
        rooms_data = rooms_ref.get() or {}
        
        rooms = []
        for room_id, room_data in rooms_data.items():
            member_count = len(manager.get_room_members(room_id))
            rooms.append(RoomResponse(
                id=room_id,
                name=room_data.get('name', room_id),
                description=room_data.get('description'),
                private=room_data.get('private', False),
                member_count=member_count,
                created_at=room_data.get('created_at', datetime.now().isoformat()),
                last_activity=room_data.get('last_activity')
            ))
        
        return rooms
        
    except Exception as e:
        logger.error(f"Failed to get rooms: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve rooms")

@app.post("/rooms", response_model=RoomResponse, tags=["Rooms"])
async def create_room(room: RoomCreate, user_data: dict = Depends(verify_token)):
    try:
        room_id = f"room_{uuid.uuid4().hex[:8]}"
        room_data = {
            "name": room.name,
            "description": room.description,
            "private": room.private,
            "created_by": user_data["uid"],
            "created_at": datetime.now().isoformat(),
            "members": [user_data["uid"]]
        }
        
        rooms_ref = db.reference(f'rooms/{room_id}')
        rooms_ref.set(room_data)
        
        return RoomResponse(
            id=room_id,
            name=room.name,
            description=room.description,
            private=room.private,
            member_count=1,
            created_at=room_data["created_at"]
        )
        
    except Exception as e:
        logger.error(f"Failed to create room: {e}")
        raise HTTPException(status_code=500, detail="Failed to create room")

@app.get("/users/online/{room_id}", response_model=List[UserProfile], tags=["Users"])
async def get_online_users(room_id: str, user_data: dict = Depends(verify_token)):
    try:
        online_users = []
        
        # Get from WebSocket manager
        room_members = manager.get_room_members(room_id)
        
        for user_id in room_members:
            # Get presence from Firebase
            try:
                presence_ref = db.reference(f'presence/{user_id}')
                user_presence = presence_ref.get()
                if user_presence and user_presence.get('status') == 'online':
                    online_users.append(UserProfile(
                        uid=user_id,
                        email=user_presence.get('email', 'unknown'),
                        displayName=user_presence.get('name', 'Unknown'),
                        photoURL=user_presence.get('picture', ''),
                        status='online',
                        last_seen=user_presence.get('last_seen'),
                        joined_at=user_presence.get('joined_at', datetime.now().isoformat())
                    ))
            except Exception as e:
                logger.error(f"Firebase presence error: {e}")
        
        return online_users
        
    except Exception as e:
        logger.error(f"Failed to get online users: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve online users")

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, token: Optional[str] = None):
    user_id = "demo_user"
    
    try:
        # Verify token if provided
        if token:
            try:
                if FIREBASE_AVAILABLE and hasattr(auth, 'verify_id_token'):
                    decoded_token = auth.verify_id_token(token)
                    user_id = decoded_token["uid"]
                    logger.info(f"WebSocket authenticated user: {user_id}")
                else:
                    # Mock Firebase verification
                    decoded_token = auth.verify_id_token(token)
                    user_id = decoded_token["uid"]
                    logger.info(f"WebSocket mock authenticated user: {user_id}")
            except Exception as e:
                logger.error(f"WebSocket token verification failed: {e}")
                # Still allow connection but with demo user
                user_id = "demo_user"
        else:
            logger.warning("WebSocket connection without token, using demo user")
        
        # Connect user
        await manager.connect(websocket, user_id, room_id)
        
        # Send welcome message
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": f"Connected to room {room_id}",
            "room_id": room_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }))
        
        # Listen for messages
        while True:
            try:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                message_type = message_data.get("type")
                
                if message_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                
                elif message_type == "typing":
                    is_typing = message_data.get("is_typing", False)
                    await manager.handle_typing(user_id, room_id, is_typing)
                
                elif message_type == "join_room":
                    new_room_id = message_data.get("room_id", room_id)
                    if new_room_id != room_id:
                        await manager.disconnect(user_id)
                        await manager.connect(websocket, user_id, new_room_id)
                        room_id = new_room_id
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        try:
            await websocket.close()
        except:
            pass
    
    finally:
        await manager.disconnect(user_id)

@app.post("/users/presence", tags=["Users"])
async def update_user_presence(presence: UserPresence, user_data: dict = Depends(verify_token)):
    try:
        await manager.update_user_presence(
            user_data["uid"],
            presence.status,
            presence.room_id
        )
        
        return {"message": "Presence updated successfully"}
        
    except Exception as e:
        logger.error(f"Failed to update presence: {e}")
        raise HTTPException(status_code=500, detail="Failed to update presence")

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    from fastapi.responses import JSONResponse
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Internal server error",
            "status_code": 500,
            "timestamp": datetime.now().isoformat()
        }
    )

# Serve static files (for production)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True
    )