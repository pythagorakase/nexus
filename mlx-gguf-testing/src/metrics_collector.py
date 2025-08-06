"""System metrics collection for MLX vs GGUF testing."""

import psutil
import subprocess
import threading
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
import json
import csv
from pathlib import Path

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects system metrics during test execution."""
    
    def __init__(self, sampling_interval: float = 0.1):
        self.sampling_interval = sampling_interval
        self.metrics: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._collecting = False
        self._thread: Optional[threading.Thread] = None
        self._start_time: Optional[float] = None
        self.process: Optional[psutil.Process] = None
        
    def start_collection(self, label: str) -> None:
        """Start collecting metrics with a specific label."""
        if self._collecting:
            logger.warning("Metrics collection already in progress")
            return
            
        self._collecting = True
        self._start_time = time.time()
        self._thread = threading.Thread(
            target=self._collect_metrics,
            args=(label,),
            daemon=True
        )
        self._thread.start()
        logger.info(f"Started metrics collection for: {label}")
    
    def stop_collection(self) -> None:
        """Stop metrics collection."""
        self._collecting = False
        if self._thread:
            self._thread.join()
        logger.info("Stopped metrics collection")
    
    def _collect_metrics(self, label: str) -> None:
        """Collect metrics in a separate thread."""
        while self._collecting:
            timestamp = time.time() - self._start_time
            metrics = {
                'timestamp': timestamp,
                'datetime': datetime.now().isoformat(),
                'memory': self._get_memory_metrics(),
                'cpu': self._get_cpu_metrics(),
            }
            
            # Try to get GPU metrics (macOS specific)
            gpu_metrics = self._get_gpu_metrics()
            if gpu_metrics:
                metrics['gpu'] = gpu_metrics
            
            self.metrics[label].append(metrics)
            time.sleep(self.sampling_interval)
    
    def _get_memory_metrics(self) -> Dict[str, float]:
        """Get memory usage metrics."""
        mem = psutil.virtual_memory()
        return {
            'total': mem.total,
            'available': mem.available,
            'percent': mem.percent,
            'used': mem.used,
            'free': mem.free,
            'active': getattr(mem, 'active', 0),
            'inactive': getattr(mem, 'inactive', 0),
            'wired': getattr(mem, 'wired', 0),
        }
    
    def _get_cpu_metrics(self) -> Dict[str, Any]:
        """Get CPU usage metrics."""
        return {
            'percent': psutil.cpu_percent(interval=None),
            'percent_per_cpu': psutil.cpu_percent(interval=None, percpu=True),
            'count': psutil.cpu_count(),
            'count_logical': psutil.cpu_count(logical=True),
        }
    
    def _get_gpu_metrics(self) -> Optional[Dict[str, Any]]:
        """Get GPU metrics (macOS specific using ioreg)."""
        try:
            # Get GPU memory usage
            result = subprocess.run(
                ['ioreg', '-l'],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            gpu_metrics = {}
            
            # Parse IOGPUMetalCommandBufferStoragePool
            for line in result.stdout.split('\n'):
                if 'IOGPUMetalCommandBufferStoragePool' in line:
                    # Extract memory values
                    if 'InUse' in line:
                        try:
                            value = int(line.split('=')[-1].strip())
                            gpu_metrics['metal_storage_in_use'] = value
                        except:
                            pass
            
            return gpu_metrics if gpu_metrics else None
            
        except Exception as e:
            logger.debug(f"Failed to get GPU metrics: {e}")
            return None
    
    def get_summary(self, label: str) -> Dict[str, Any]:
        """Get summary statistics for a collection label."""
        if label not in self.metrics:
            return {}
        
        data = self.metrics[label]
        if not data:
            return {}
        
        # Calculate memory statistics
        memory_values = [m['memory']['used'] for m in data]
        memory_percents = [m['memory']['percent'] for m in data]
        cpu_percents = [m['cpu']['percent'] for m in data]
        
        return {
            'duration': data[-1]['timestamp'],
            'samples': len(data),
            'memory': {
                'initial_mb': memory_values[0] / (1024 * 1024),
                'peak_mb': max(memory_values) / (1024 * 1024),
                'final_mb': memory_values[-1] / (1024 * 1024),
                'avg_percent': sum(memory_percents) / len(memory_percents),
                'peak_percent': max(memory_percents),
            },
            'cpu': {
                'avg_percent': sum(cpu_percents) / len(cpu_percents),
                'peak_percent': max(cpu_percents),
            }
        }
    
    def save_to_csv(self, output_dir: Path) -> None:
        """Save collected metrics to CSV files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for label, data in self.metrics.items():
            if not data:
                continue
                
            csv_path = output_dir / f"{label}_metrics.csv"
            
            # Flatten the nested structure for CSV
            rows = []
            for entry in data:
                row = {
                    'timestamp': entry['timestamp'],
                    'datetime': entry['datetime'],
                    'memory_used_mb': entry['memory']['used'] / (1024 * 1024),
                    'memory_percent': entry['memory']['percent'],
                    'memory_available_mb': entry['memory']['available'] / (1024 * 1024),
                    'cpu_percent': entry['cpu']['percent'],
                }
                
                # Add GPU metrics if available
                if 'gpu' in entry and entry['gpu']:
                    for key, value in entry['gpu'].items():
                        row[f'gpu_{key}'] = value
                
                rows.append(row)
            
            # Write to CSV
            if rows:
                fieldnames = rows[0].keys()
                with open(csv_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                
                logger.info(f"Saved metrics to {csv_path}")
    
    def save_to_json(self, output_dir: Path) -> None:
        """Save collected metrics to JSON files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for label, data in self.metrics.items():
            if not data:
                continue
                
            json_path = output_dir / f"{label}_metrics.json"
            
            with open(json_path, 'w') as f:
                json.dump({
                    'label': label,
                    'sampling_interval': self.sampling_interval,
                    'data': data,
                    'summary': self.get_summary(label)
                }, f, indent=2)
            
            logger.info(f"Saved metrics to {json_path}")
    
    def clear(self) -> None:
        """Clear all collected metrics."""
        self.metrics.clear()