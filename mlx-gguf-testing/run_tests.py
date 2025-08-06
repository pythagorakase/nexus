#!/usr/bin/env python3
"""Main entry point for MLX vs GGUF testing."""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config_manager import ConfigManager
from src.test_runner import TestRunner
from src.results_analyzer import ResultsAnalyzer


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('mlx_gguf_testing.log')
        ]
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MLX vs GGUF Performance Testing Framework"
    )
    
    parser.add_argument(
        '--config',
        default='config/test_config.yaml',
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--analyze-only',
        type=str,
        metavar='RESULTS_DIR',
        help='Only analyze existing results from specified directory'
    )
    
    parser.add_argument(
        '--single-test',
        nargs=3,
        metavar=('MODEL_ID', 'MODEL_TYPE', 'SCENARIO'),
        help='Run a single test (model_id, model_type, scenario)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Analyze only mode
        if args.analyze_only:
            logger.info(f"Analyzing results from {args.analyze_only}")
            analyzer = ResultsAnalyzer(Path(args.analyze_only))
            report = analyzer.generate_report()
            analyzer.generate_plots()
            print(f"\nReport saved to: {args.analyze_only}/report.md")
            return
        
        # Load configuration
        config = ConfigManager(args.config)
        
        # Create test runner
        runner = TestRunner(config)
        
        # Run tests
        if args.single_test:
            model_id, model_type, scenario = args.single_test
            logger.info(f"Running single test: {model_id} ({model_type}) - {scenario}")
            result = runner.run_single_test(model_id, model_type, scenario)
            
            if result.errors:
                logger.error(f"Test failed: {', '.join(result.errors)}")
            else:
                logger.info(f"Test completed successfully")
                logger.info(f"Metrics: {result.metrics}")
        else:
            logger.info("Starting MLX vs GGUF performance tests")
            runner.run_all_tests()
            
            # Analyze results
            output_config = config.get_output_config()
            latest_results = sorted(
                Path(output_config['results_dir']).iterdir(),
                key=lambda x: x.stat().st_mtime
            )[-1]
            
            logger.info(f"\nAnalyzing results...")
            analyzer = ResultsAnalyzer(latest_results)
            report = analyzer.generate_report()
            
            if output_config.get('generate_plots', True):
                analyzer.generate_plots()
            
            print(f"\n{'='*60}")
            print("Test run completed!")
            print(f"Results saved to: {latest_results}")
            print(f"Report available at: {latest_results}/report.md")
            print(f"{'='*60}")
    
    except KeyboardInterrupt:
        logger.info("\nTest run interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Test run failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()