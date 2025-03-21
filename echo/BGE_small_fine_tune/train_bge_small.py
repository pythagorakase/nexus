#!/usr/bin/env python3
"""
Fine-tune BGE-small embedding model with triplet data
"""

import os
import json
import glob
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Any

import torch
from sentence_transformers import SentenceTransformer, InputExample, losses
from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator
from torch.utils.data import DataLoader
import random

# Configure logging
logging.basicConfig(format='%(asctime)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

def load_triplets(filepath: str) -> List[Dict[str, str]]:
    """Load triplets from a JSON file"""
    logger.info(f"Loading triplets from {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    logger.info(f"Loaded {len(data)} triplets")
    return data

def prepare_training_data(triplets: List[Dict[str, str]], max_samples=None):
    """Convert triplets to SentenceTransformer training examples"""
    examples = []
    
    # Shuffle to ensure diverse batches
    random.shuffle(triplets)
    
    # Limit samples if specified
    if max_samples and max_samples < len(triplets):
        triplets = triplets[:max_samples]
    
    # Convert each triplet to an InputExample
    for i, triplet in enumerate(triplets):
        query = triplet['query']
        positive = triplet['positive']
        negative = triplet['negative']
        
        examples.append(InputExample(texts=[query, positive, negative]))
    
    logger.info(f"Created {len(examples)} training examples")
    return examples

def create_train_eval_split(examples, eval_fraction=0.1):
    """Split examples into training and evaluation sets"""
    # Shuffle examples
    random.shuffle(examples)
    
    # Calculate split
    eval_size = max(1, int(len(examples) * eval_fraction))
    train_size = len(examples) - eval_size
    
    logger.info(f"Splitting data: {train_size} training, {eval_size} evaluation examples")
    
    return examples[:train_size], examples[train_size:]

def estimate_training_time(num_examples, batch_size, epochs):
    """Provide a rough estimate of training time"""
    # Very rough estimates based on typical performance
    steps_per_epoch = num_examples // batch_size
    time_per_step = 0.1  # seconds, adjust based on your hardware
    
    total_steps = steps_per_epoch * epochs
    estimated_seconds = total_steps * time_per_step
    
    hours = estimated_seconds // 3600
    minutes = (estimated_seconds % 3600) // 60
    
    return f"Estimated training time: {hours} hours, {minutes} minutes (rough estimate)"

def fine_tune_model(model_name: str, 
                    training_examples: List[InputExample], 
                    evaluation_examples: List[InputExample] = None,
                    output_dir: str = None,
                    batch_size: int = 16,
                    epochs: int = 3,
                    warmup_steps: int = 100,
                    use_amp: bool = False):
    """Fine-tune the model with the provided examples"""
    
    # Create output directory if not specified
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"bge_small_finetuned_{timestamp}"
    
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Output will be saved to {output_dir}")
    
    # Load model from HuggingFace
    logger.info(f"Loading model: {model_name}")
    model = SentenceTransformer(model_name)
    
    # Explicitly ensure model is using FP32
    logger.info("Using FP32 precision (full precision)")
    
    # Prepare data loader
    train_dataloader = DataLoader(training_examples, shuffle=True, batch_size=batch_size)
    
    # Use triplet loss for training
    train_loss = losses.TripletLoss(model=model)
    
    # Set up evaluator if we have evaluation examples
    evaluator = None
    if evaluation_examples and len(evaluation_examples) > 0:
        logger.info("Setting up evaluator with evaluation examples")
        evaluator = EmbeddingSimilarityEvaluator.from_input_examples(evaluation_examples)
    
    # Print training estimate
    logger.info(estimate_training_time(len(training_examples), batch_size, epochs))
    
    # Start training
    logger.info(f"Starting training with {len(training_examples)} examples, {epochs} epochs")
    
    # Train the model
    model.fit(train_objectives=[(train_dataloader, train_loss)],
              evaluator=evaluator,
              epochs=epochs,
              evaluation_steps=1000,
              warmup_steps=warmup_steps,
              output_path=output_dir,
              use_amp=use_amp,
              show_progress_bar=True)
    
    logger.info(f"Training complete. Model saved to {output_dir}")
    return model, output_dir

def main():
    parser = argparse.ArgumentParser(description='Fine-tune BGE-small embedding model')
    parser.add_argument('--model', type=str, 
                        default='BAAI/bge-small-en-v1.5',  # Use the HuggingFace model ID
                        help='Model name or path (default: BAAI/bge-small-en-v1.5)')
    parser.add_argument('--data', type=str, help='Path to the triplet JSON file')
    parser.add_argument('--output', type=str, help='Output directory for fine-tuned model')
    parser.add_argument('--batch-size', type=int, default=16, help='Training batch size')
    parser.add_argument('--epochs', type=int, default=3, help='Number of training epochs')
    parser.add_argument('--max-samples', type=int, default=None, 
                        help='Maximum number of training samples to use (for testing)')
    parser.add_argument('--eval-fraction', type=float, default=0.1,
                        help='Fraction of data to use for evaluation')
    parser.add_argument('--use-amp', action='store_true', 
                        help='Enable Automatic Mixed Precision training (default: disabled)')
    parser.add_argument('--warmup-steps', type=int, default=100,
                        help='Number of warmup steps for learning rate scheduler')
    
    args = parser.parse_args()
    
    # If no data file is specified, find JSON files in the current directory
    if args.data is None:
        json_files = glob.glob("*.json")
        if not json_files:
            logger.error("No JSON files found in the current directory")
            return
        
        # Use the largest JSON file (assuming it's the data file)
        data_file = max(json_files, key=lambda x: os.path.getsize(x))
        logger.info(f"Using data file: {data_file}")
    else:
        data_file = args.data
    
    # Load data
    triplets = load_triplets(data_file)
    
    # Prepare training data
    training_examples = prepare_training_data(triplets, args.max_samples)
    
    # Split into train and eval
    train_examples, eval_examples = create_train_eval_split(
        training_examples, 
        eval_fraction=args.eval_fraction
    )
    
    # Fine-tune the model
    fine_tune_model(
        model_name=args.model,
        training_examples=train_examples,
        evaluation_examples=eval_examples,
        output_dir=args.output,
        batch_size=args.batch_size,
        epochs=args.epochs,
        warmup_steps=args.warmup_steps,
        use_amp=args.use_amp
    )

if __name__ == "__main__":
    main()