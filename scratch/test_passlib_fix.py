from passlib.context import CryptContext

def test_passlib():
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    password = "lwt050520"
    print(f"Testing password: {password}")
    
    hashed = pwd_context.hash(password)
    print(f"Hashed: {hashed}")
    
    is_valid = pwd_context.verify(password, hashed)
    print(f"Verified: {is_valid}")
    
    # Test 72+ char password
    long_pw = "a" * 100
    hashed_long = pwd_context.hash(long_pw)
    print(f"Hashed long (len 100): {hashed_long}")
    is_valid_long = pwd_context.verify(long_pw, hashed_long)
    print(f"Verified long: {is_valid_long}")

if __name__ == "__main__":
    try:
        test_passlib()
    except Exception as e:
        print(f"Error: {e}")
