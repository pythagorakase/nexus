"""Analysis and reporting for MLX vs GGUF test results."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class ResultsAnalyzer:
    """Analyzes test results and generates reports."""
    
    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.test_results = self._load_test_results()
        self.metrics_data = self._load_metrics_data()
    
    def _load_test_results(self) -> Dict[str, Any]:
        """Load test results from JSON."""
        results_file = self.results_dir / 'test_results.json'
        if not results_file.exists():
            raise FileNotFoundError(f"Test results not found: {results_file}")
        
        with open(results_file, 'r') as f:
            return json.load(f)
    
    def _load_metrics_data(self) -> Dict[str, pd.DataFrame]:
        """Load metrics data from CSV files."""
        metrics_data = {}
        metrics_dir = self.results_dir / 'metrics'
        
        if metrics_dir.exists():
            for csv_file in metrics_dir.glob('*.csv'):
                label = csv_file.stem.replace('_metrics', '')
                try:
                    metrics_data[label] = pd.read_csv(csv_file)
                except Exception as e:
                    logger.error(f"Failed to load {csv_file}: {e}")
        
        return metrics_data
    
    def generate_report(self) -> str:
        """Generate comprehensive markdown report."""
        report_lines = [
            "# MLX vs GGUF Performance Test Report",
            f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"\nTest Run Summary:",
            f"- Total tests: {self.test_results['test_run']['total_tests']}",
            f"- Failed tests: {self.test_results['test_run']['failed_tests']}",
            f"- Interrupted: {'Yes' if self.test_results['test_run']['interrupted'] else 'No'}",
            "\n## Executive Summary\n"
        ]
        
        # Analyze results by model pair
        model_comparisons = self._analyze_model_comparisons()
        
        for model_name, comparison in model_comparisons.items():
            report_lines.append(f"\n### {model_name}")
            
            # Memory comparison
            if 'memory' in comparison:
                mem = comparison['memory']
                report_lines.extend([
                    "\n**Memory Usage:**",
                    f"- GGUF: {mem.get('gguf_peak_mb', 'N/A'):.1f} MB (peak)",
                    f"- MLX: {mem.get('mlx_peak_mb', 'N/A'):.1f} MB (peak)",
                    f"- Difference: {mem.get('difference_mb', 'N/A'):.1f} MB ({mem.get('difference_percent', 'N/A'):.1f}%)"
                ])
            
            # Performance comparison
            if 'performance' in comparison:
                perf = comparison['performance']
                report_lines.extend([
                    "\n**Performance:**",
                    f"- GGUF tokens/sec: {perf.get('gguf_tps', 'N/A'):.1f}",
                    f"- MLX tokens/sec: {perf.get('mlx_tps', 'N/A'):.1f}",
                    f"- GGUF TTFT: {perf.get('gguf_ttft', 'N/A'):.2f}s",
                    f"- MLX TTFT: {perf.get('mlx_ttft', 'N/A'):.2f}s"
                ])
        
        # Detailed results by scenario
        report_lines.append("\n## Detailed Results by Scenario\n")
        
        scenarios = ['cold_start', 'simple_gen', 'context_stress', 'memory_leak', 'moe_specific']
        for scenario in scenarios:
            scenario_results = self._get_scenario_results(scenario)
            if scenario_results:
                report_lines.extend(self._format_scenario_results(scenario, scenario_results))
        
        # Memory leak analysis
        report_lines.extend(self._analyze_memory_leaks())
        
        # MoE-specific analysis
        report_lines.extend(self._analyze_moe_patterns())
        
        # Recommendations
        report_lines.extend(self._generate_recommendations())
        
        # Save report
        report_path = self.results_dir / 'report.md'
        report_content = '\n'.join(report_lines)
        
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        logger.info(f"Report saved to {report_path}")
        return report_content
    
    def _analyze_model_comparisons(self) -> Dict[str, Dict[str, Any]]:
        """Compare GGUF vs MLX for each model."""
        comparisons = {}
        
        # Group results by model name
        model_results = {}
        for result in self.test_results['results']:
            model_name = result['model_id'].split('/')[-1].split('@')[0]
            if model_name not in model_results:
                model_results[model_name] = {'gguf': [], 'mlx': []}
            model_results[model_name][result['model_type']].append(result)
        
        # Compare each model
        for model_name, results in model_results.items():
            comparison = {}
            
            # Memory comparison
            gguf_memory = self._get_peak_memory(results['gguf'])
            mlx_memory = self._get_peak_memory(results['mlx'])
            
            if gguf_memory and mlx_memory:
                comparison['memory'] = {
                    'gguf_peak_mb': gguf_memory,
                    'mlx_peak_mb': mlx_memory,
                    'difference_mb': gguf_memory - mlx_memory,
                    'difference_percent': ((gguf_memory - mlx_memory) / gguf_memory) * 100
                }
            
            # Performance comparison
            gguf_perf = self._get_performance_metrics(results['gguf'])
            mlx_perf = self._get_performance_metrics(results['mlx'])
            
            if gguf_perf and mlx_perf:
                comparison['performance'] = {
                    'gguf_tps': gguf_perf['tokens_per_second'],
                    'mlx_tps': mlx_perf['tokens_per_second'],
                    'gguf_ttft': gguf_perf['ttft'],
                    'mlx_ttft': mlx_perf['ttft']
                }
            
            comparisons[model_name] = comparison
        
        return comparisons
    
    def _get_peak_memory(self, results: List[Dict[str, Any]]) -> Optional[float]:
        """Get peak memory usage from results."""
        peak_memory = None
        
        for result in results:
            if 'memory_summary' in result.get('metrics', {}):
                mem = result['metrics']['memory_summary'].get('peak_mb', 0)
                if peak_memory is None or mem > peak_memory:
                    peak_memory = mem
        
        return peak_memory
    
    def _get_performance_metrics(self, results: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        """Get average performance metrics."""
        tps_values = []
        ttft_values = []
        
        for result in results:
            if 'generation_metrics' in result.get('metrics', {}):
                gen = result['metrics']['generation_metrics']
                if gen.get('tokens_per_second'):
                    tps_values.append(gen['tokens_per_second'])
                if gen.get('ttft'):
                    ttft_values.append(gen['ttft'])
        
        if tps_values and ttft_values:
            return {
                'tokens_per_second': np.mean(tps_values),
                'ttft': np.mean(ttft_values)
            }
        
        return None
    
    def _get_scenario_results(self, scenario: str) -> List[Dict[str, Any]]:
        """Get all results for a specific scenario."""
        return [r for r in self.test_results['results'] if r['scenario'] == scenario]
    
    def _format_scenario_results(self, scenario: str, results: List[Dict[str, Any]]) -> List[str]:
        """Format results for a specific scenario."""
        lines = [f"\n### {scenario.replace('_', ' ').title()}\n"]
        
        # Group by model
        by_model = {}
        for result in results:
            model = result['model_id']
            if model not in by_model:
                by_model[model] = []
            by_model[model].append(result)
        
        for model, model_results in by_model.items():
            lines.append(f"\n**{model}:**")
            
            for result in model_results:
                model_type = result['model_type'].upper()
                if result['errors']:
                    lines.append(f"- {model_type}: Failed - {', '.join(result['errors'])}")
                else:
                    # Format key metrics based on scenario
                    if scenario == 'memory_leak':
                        growth = result['metrics'].get('memory_growth_mb', 0)
                        lines.append(f"- {model_type}: Memory growth: {growth:.1f} MB")
                    elif scenario in ['simple_gen', 'context_stress']:
                        gen = result['metrics'].get('generation_metrics', {})
                        tps = gen.get('tokens_per_second', 0)
                        ttft = gen.get('ttft', 0)
                        if tps is not None and ttft is not None:
                            lines.append(f"- {model_type}: {tps:.1f} tokens/sec, TTFT: {ttft:.2f}s")
                        else:
                            lines.append(f"- {model_type}: No performance metrics available")
        
        return lines
    
    def _analyze_memory_leaks(self) -> List[str]:
        """Analyze memory leak test results."""
        lines = ["\n## Memory Leak Analysis\n"]
        
        leak_results = self._get_scenario_results('memory_leak')
        if not leak_results:
            return lines
        
        for result in leak_results:
            if result['errors']:
                continue
                
            model = result['model_id']
            model_type = result['model_type'].upper()
            growth = result['metrics'].get('memory_growth_mb', 0)
            per_iter = result['metrics'].get('growth_per_iteration_mb', 0)
            
            lines.extend([
                f"\n**{model} ({model_type}):**",
                f"- Total memory growth: {growth:.1f} MB",
                f"- Growth per iteration: {per_iter:.2f} MB",
                f"- Leak severity: {'High' if per_iter > 10 else 'Medium' if per_iter > 5 else 'Low'}"
            ])
        
        return lines
    
    def _analyze_moe_patterns(self) -> List[str]:
        """Analyze MoE-specific test results."""
        lines = ["\n## MoE Expert Routing Analysis\n"]
        
        moe_results = self._get_scenario_results('moe_specific')
        if not moe_results:
            return lines
        
        for result in moe_results:
            if result['errors'] or 'expert_results' not in result['metrics']:
                continue
            
            model = result['model_id']
            model_type = result['model_type'].upper()
            expert_results = result['metrics']['expert_results']
            
            lines.append(f"\n**{model} ({model_type}):**")
            
            for expert_type, metrics in expert_results.items():
                tps = metrics.get('tokens_per_second', 0)
                ttft = metrics.get('ttft', 0)
                if tps is not None and ttft is not None:
                    lines.append(f"- {expert_type}: {tps:.1f} tokens/sec, TTFT: {ttft:.2f}s")
                else:
                    lines.append(f"- {expert_type}: No performance metrics available")
        
        return lines
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on results."""
        lines = ["\n## Recommendations\n"]
        
        # Analyze overall patterns
        model_comparisons = self._analyze_model_comparisons()
        
        # Memory efficiency recommendations
        memory_winner = None
        best_memory_savings = 0
        
        for model, comparison in model_comparisons.items():
            if 'memory' in comparison:
                savings = comparison['memory']['difference_percent']
                if savings > best_memory_savings:
                    best_memory_savings = savings
                    memory_winner = 'MLX' if comparison['memory']['mlx_peak_mb'] < comparison['memory']['gguf_peak_mb'] else 'GGUF'
        
        if memory_winner:
            lines.append(f"- **Memory Efficiency**: {memory_winner} format shows better memory efficiency with up to {best_memory_savings:.1f}% savings")
        
        # Performance recommendations
        lines.append("\n### Model-Specific Recommendations:")
        
        for model, comparison in model_comparisons.items():
            if 'performance' in comparison and 'memory' in comparison:
                perf = comparison['performance']
                mem = comparison['memory']
                
                # Determine best format for this model
                if mem['mlx_peak_mb'] < mem['gguf_peak_mb'] and perf['mlx_tps'] > perf['gguf_tps'] * 0.9:
                    recommendation = "MLX (better memory efficiency with comparable performance)"
                elif perf['gguf_tps'] > perf['mlx_tps'] * 1.2:
                    recommendation = "GGUF (significantly better performance)"
                else:
                    recommendation = "Either format (similar performance, choose based on memory constraints)"
                
                lines.append(f"- **{model}**: Recommend {recommendation}")
        
        # NEXUS LORE specific recommendations
        lines.extend([
            "\n### For NEXUS LORE Implementation:",
            "- For Scout 17Bx16E: Check memory leak severity before choosing format",
            "- Consider MLX if memory constraints are tight and context window can be limited to 40k tokens",
            "- Use GGUF if you need the full 131k context window",
            "- Monitor memory usage closely during extended sessions"
        ])
        
        return lines
    
    def generate_plots(self) -> None:
        """Generate visualization plots."""
        plots_dir = self.results_dir / 'plots'
        plots_dir.mkdir(exist_ok=True)
        
        # Memory comparison plot
        self._plot_memory_comparison(plots_dir)
        
        # Performance comparison plot
        self._plot_performance_comparison(plots_dir)
        
        # Memory timeline plots
        self._plot_memory_timelines(plots_dir)
    
    def _plot_memory_comparison(self, output_dir: Path) -> None:
        """Plot memory usage comparison."""
        comparisons = self._analyze_model_comparisons()
        
        if not comparisons:
            return
        
        models = []
        gguf_memory = []
        mlx_memory = []
        
        for model, comp in comparisons.items():
            if 'memory' in comp:
                models.append(model)
                gguf_memory.append(comp['memory']['gguf_peak_mb'])
                mlx_memory.append(comp['memory']['mlx_peak_mb'])
        
        if not models:
            return
        
        x = np.arange(len(models))
        width = 0.35
        
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(x - width/2, gguf_memory, width, label='GGUF', color='#2E86AB')
        ax.bar(x + width/2, mlx_memory, width, label='MLX', color='#A23B72')
        
        ax.set_xlabel('Model')
        ax.set_ylabel('Peak Memory Usage (MB)')
        ax.set_title('Memory Usage Comparison: GGUF vs MLX')
        ax.set_xticks(x)
        ax.set_xticklabels(models, rotation=45, ha='right')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_dir / 'memory_comparison.png', dpi=150)
        plt.close()
    
    def _plot_performance_comparison(self, output_dir: Path) -> None:
        """Plot performance comparison."""
        comparisons = self._analyze_model_comparisons()
        
        if not comparisons:
            return
        
        models = []
        gguf_tps = []
        mlx_tps = []
        
        for model, comp in comparisons.items():
            if 'performance' in comp:
                models.append(model)
                gguf_tps.append(comp['performance']['gguf_tps'])
                mlx_tps.append(comp['performance']['mlx_tps'])
        
        if not models:
            return
        
        x = np.arange(len(models))
        width = 0.35
        
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(x - width/2, gguf_tps, width, label='GGUF', color='#2E86AB')
        ax.bar(x + width/2, mlx_tps, width, label='MLX', color='#A23B72')
        
        ax.set_xlabel('Model')
        ax.set_ylabel('Tokens per Second')
        ax.set_title('Performance Comparison: GGUF vs MLX')
        ax.set_xticks(x)
        ax.set_xticklabels(models, rotation=45, ha='right')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_dir / 'performance_comparison.png', dpi=150)
        plt.close()
    
    def _plot_memory_timelines(self, output_dir: Path) -> None:
        """Plot memory usage over time for each test."""
        for label, df in self.metrics_data.items():
            if df.empty:
                continue
            
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.plot(df['timestamp'], df['memory_used_mb'], linewidth=2, color='#2E86AB')
            
            ax.set_xlabel('Time (seconds)')
            ax.set_ylabel('Memory Usage (MB)')
            ax.set_title(f'Memory Usage Timeline: {label}')
            ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(output_dir / f'memory_timeline_{label}.png', dpi=150)
            plt.close()