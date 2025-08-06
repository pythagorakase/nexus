#!/bin/bash
# Script to test temporal search functionality

# Set environment variables if needed
export PYTHONPATH="/Users/pythagor/nexus:$PYTHONPATH"

# Default values
BOOST_FACTOR=0.5
EARLY_QUERY="Tell me about the first meeting between Alex and Emilia"
RECENT_QUERY="What is the current situation with Alex and Emilia?"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --boost-factor)
      BOOST_FACTOR="$2"
      shift 2
      ;;
    --early-query)
      EARLY_QUERY="$2"
      shift 2
      ;;
    --recent-query)
      RECENT_QUERY="$2"
      shift 2
      ;;
    --classification-only)
      CLASSIFICATION_ONLY="--classification-only"
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--boost-factor VALUE] [--early-query QUERY] [--recent-query QUERY] [--classification-only]"
      exit 1
      ;;
  esac
done

# Run the test script
echo "Running temporal search test with:"
echo "  Boost factor: $BOOST_FACTOR"
echo "  Early query: $EARLY_QUERY"
echo "  Recent query: $RECENT_QUERY"
echo "  Classification only: ${CLASSIFICATION_ONLY:-No}"
echo

# Execute the test script
python3 test_temporal_search.py \
  --boost-factor $BOOST_FACTOR \
  --early-query "$EARLY_QUERY" \
  --recent-query "$RECENT_QUERY" \
  $CLASSIFICATION_ONLY

# Exit with the same status code as the test script
exit $?