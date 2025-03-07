import os
import chromadb
import logging
from sentence_transformers import SentenceTransformer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chroma_repair")

# Path to ChromaDB
CHROMA_PATH = "./chroma_db"

def diagnose_and_repair():
    """Diagnose and repair ChromaDB collections"""
    logger.info("Starting ChromaDB collection diagnosis")
    
    # Initialize the client
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    
    # Check what collections actually exist according to ChromaDB
    try:
        # In v0.6.0, list_collections returns just the names
        existing_collections = client.list_collections()
        logger.info(f"Collections recognized by ChromaDB: {existing_collections}")
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        # Try an alternative approach
        try:
            logger.info("Trying alternative method to list collections")
            # Try to get collections individually
            test_collections = ["transcripts", "transcripts_bge_large", "transcripts_e5_large", "transcripts_bge_small"]
            existing_collections = []
            for coll_name in test_collections:
                try:
                    coll = client.get_collection(name=coll_name)
                    existing_collections.append(coll_name)
                    logger.info(f"Found collection: {coll_name}")
                except Exception:
                    logger.info(f"Collection {coll_name} does not exist")
        except Exception as e2:
            logger.error(f"Alternative approach failed: {e2}")
            return
    
    # Collection names we expect
    expected_collections = [
        "transcripts",
        "transcripts_bge_large",
        "transcripts_e5_large", 
        "transcripts_bge_small"
    ]
    
    # Check directory structure
    logger.info("Checking directory structure")
    db_dirs = os.listdir(CHROMA_PATH)
    logger.info(f"Directories in ChromaDB path: {db_dirs}")
    
    # Check if legacy collection exists and has data
    try:
        legacy_collection = client.get_collection(name="transcripts")
        count = legacy_collection.count()
        logger.info(f"Legacy collection 'transcripts' has {count} chunks")
        
        if count == 0:
            logger.error("Legacy collection is empty - no source data")
            return
            
        # Get a sample of data from the legacy collection
        logger.info("Retrieving sample data from legacy collection")
        sample_data = legacy_collection.get(limit=5, include=["documents", "metadatas", "embeddings"])
    except Exception as e:
        logger.error(f"Error accessing legacy collection: {e}")
        return
    
    # Recreate missing collections
    for collection_name in expected_collections:
        if collection_name not in existing_collections and collection_name != "transcripts":
            logger.info(f"Recreating collection: {collection_name}")
            
            # Determine which model to use
            if collection_name == "transcripts_bge_large":
                model_name = "BAAI/bge-large-en"
            elif collection_name == "transcripts_e5_large":
                model_name = "intfloat/e5-large-v2"
            elif collection_name == "transcripts_bge_small":
                model_name = "BAAI/bge-small-en"
            else:
                continue
                
            # Load the model
            logger.info(f"Loading model: {model_name}")
            try:
                model = SentenceTransformer(model_name)
            except Exception as e:
                logger.error(f"Error loading model {model_name}: {e}")
                continue
                
            # Create the collection
            try:
                # Delete the collection if it exists but ChromaDB doesn't recognize it
                if os.path.exists(os.path.join(CHROMA_PATH, collection_name)):
                    logger.info(f"Directory for {collection_name} exists but collection is not recognized.")
                    logger.info(f"Will try to create a new collection with the same name.")
                
                new_collection = client.create_collection(name=collection_name)
                
                # Process and transfer a small test batch
                logger.info(f"Transferring test batch of 5 documents to {collection_name}")
                for i in range(min(5, len(sample_data["ids"]))):
                    doc = sample_data["documents"][i]
                    metadata = sample_data["metadatas"][i].copy()  # Make a copy to avoid modifying the original
                    
                    # Add processing_version to metadata
                    metadata["processing_version"] = "1.0.0-triple"
                    
                    # Generate embedding with the appropriate model
                    embedding = model.encode(doc).tolist()
                    
                    # Add to the new collection
                    new_collection.add(
                        ids=[sample_data["ids"][i]],
                        documents=[doc],
                        embeddings=[embedding],
                        metadatas=[metadata]
                    )
                    
                logger.info(f"Successfully created and populated test data for {collection_name}")
            except Exception as e:
                logger.error(f"Error creating collection {collection_name}: {e}")
    
    # Verify collections now exist
    try:
        existing_collections = client.list_collections()
        logger.info(f"Collections after repair: {existing_collections}")
        
        # Return success/failure message
        missing = [c for c in expected_collections if c not in existing_collections]
        if missing:
            logger.error(f"Still missing collections: {missing}")
            return f"Partial repair completed. Still missing: {missing}"
        else:
            logger.info("All collections successfully repaired/verified")
            return "Repair successful. Run encode_chunks.py again to process all chunks."
    except Exception as e:
        logger.error(f"Error verifying collections: {e}")
        return "Unable to verify collections."

if __name__ == "__main__":
    result = diagnose_and_repair()
    print(result)