import chromadb
import sys
import os

# Set custom path if needed
path = r"c:\Users\25380\Desktop\学习\软件工程\Project\源代码\team-project-26spring-26s-13\data\chromadb"

def inspect_chroma():
    try:
        client = chromadb.PersistentClient(path=path)
        collections = client.list_collections()
        print(f"Found {len(collections)} collections.")
        for col_name in collections:
            col = client.get_collection(name=col_name.name)
            count = col.count()
            print(f"Collection: {col_name.name}, Count: {count}")
            if count > 0:
                peek = col.peek(limit=1)
                print(f"  Peek Metadata: {peek['metadatas']}")
                # print(f"  Peek Document: {peek['documents'][0][:100]}...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_chroma()
