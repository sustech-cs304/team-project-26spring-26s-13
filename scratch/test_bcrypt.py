import bcrypt

def test_bcrypt():
    password = "lwt050520"
    print(f"Testing password: {password}")
    
    # Simulate the code in auth_service.py
    safe_password = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    print(f"Safe password: {safe_password} (len: {len(safe_password)})")
    
    try:
        pw_bytes = safe_password.encode('utf-8')
        print(f"Password bytes len: {len(pw_bytes)}")
        
        hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt())
        print(f"Hashed: {hashed.decode('utf-8')}")
        
        # Test long password
        long_pw = "a" * 100
        safe_long = long_pw.encode("utf-8")[:72].decode("utf-8", errors="ignore")
        print(f"Safe long password len: {len(safe_long)}")
        hashed_long = bcrypt.hashpw(safe_long.encode('utf-8'), bcrypt.gensalt())
        print("Successfully hashed 72-byte truncated password.")
        
    except Exception as e:
        print(f"Error encountered: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_bcrypt()
