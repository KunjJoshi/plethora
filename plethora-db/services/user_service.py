from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from models.user import User, UserType, UserStatus
from schemas.user import UserCreateWithUUID, UserInDB, UserUpdate
from auth.jwt import verify_supabase_jwt, extract_provider


def insert_into_db_user(db: Session, user: UserCreateWithUUID) -> UserInDB:
    try:
        email = user.email
        user_exists = db.query(User).filter(User.email == email).first()
        if user_exists:
            raise ValueError("User already exists")
        new_user = User(
            id=user.id,
            email=user.email,
            username=user.username,
            name=user.name,
            address=user.address,
            user_type=UserType.SINGLE_USER,
            user_status=UserStatus.ACTIVE,
            is_active=True
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return UserInDB(
            id=new_user.id,
            email=new_user.email,
            username=new_user.username,
            name=new_user.name,
            address=new_user.address,
            user_type=new_user.user_type,
            user_status=new_user.user_status,
            is_active=new_user.is_active,
            created_at=new_user.created_at,
            updated_at=new_user.updated_at
        )
    except IntegrityError as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise e


def get_user_by_email(db: Session, email: str) -> UserInDB:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise ValueError("User not found")
    return UserInDB.model_validate(user)


def get_user_by_id(db: Session, user_id: str) -> UserInDB:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    return UserInDB.model_validate(user)


def update_user_profile(db: Session, user_id: str, update_data: UserUpdate) -> UserInDB:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    try:
        db.commit()
        db.refresh(user)
        return UserInDB.model_validate(user)
    except IntegrityError:
        db.rollback()
        raise ValueError("Username is already taken")


def verify_login_attempt(db: Session, email: str, token: str) -> UserInDB:
    # Verify JWT signature, expiry, and audience before touching the DB
    payload = verify_supabase_jwt(token)

    token_email = payload.get("email")
    if token_email != email:
        raise ValueError("Token does not match the provided email")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise ValueError("No account found with this email")
    if user.user_status == UserStatus.SUSPENDED:
        raise ValueError("Account is suspended")
    if user.user_status == UserStatus.DELETED:
        raise ValueError("Account not found")
    if not user.is_active:
        raise ValueError("Account is not active. Please verify your email first.")

    return UserInDB.model_validate(user)


def verify_or_create_oauth_user(db: Session, token: str) -> UserInDB:
    """
    Verify an OAuth JWT and upsert the user into public.users.

    Called after any Supabase OAuth flow (Google, Outlook, GitHub, etc.).
    The JWT payload contains the provider name and user metadata — we treat
    all providers uniformly since Supabase re-signs the token.
    """
    payload = verify_supabase_jwt(token)

    user_id = payload.get("sub")   # local JWT payload: UUID is in "sub"
    email = payload.get("email")
    provider = extract_provider(payload)
    user_metadata = payload.get("user_metadata", {})

    if not user_id or not email:
        raise ValueError("Invalid token: missing user identity")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if existing.user_status == UserStatus.SUSPENDED:
            raise ValueError("Account is suspended")
        if existing.user_status == UserStatus.DELETED:
            raise ValueError("Account not found")
        return UserInDB.model_validate(existing)

    # First-time OAuth login — auto-provision the user record.
    # Username defaults to the email prefix; user can update it later.
    name = user_metadata.get("full_name") or user_metadata.get("name")
    username = email.split("@")[0]

    new_user = User(
        id=user_id,
        email=email,
        username=username,
        name=name,
        user_type=UserType.SINGLE_USER,
        user_status=UserStatus.ACTIVE,
        is_active=True,
    )
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return UserInDB.model_validate(new_user)
    except IntegrityError:
        db.rollback()
        # Username collision: append part of the UUID to make it unique
        new_user.username = f"{username}_{str(user_id)[:6]}"
        try:
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            return UserInDB.model_validate(new_user)
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Could not provision account for {provider} login. Please try again.")
