/**
 * API client for Apex Audition endpoints.
 *
 * All functions return promises that can be used with TanStack Query.
 */

const API_BASE = import.meta.env.VITE_AUDITION_API_URL ?? '/api/audition';

export interface Condition {
  id: number;
  slug: string;
  provider: string;
  model_name: string;
  label?: string;
  temperature?: number | null;
  reasoning_effort?: string | null;
  thinking_enabled?: boolean | null;
  max_output_tokens?: number | null;
  thinking_budget_tokens?: number | null;
  is_active: boolean;
  notes?: Array<{ text: string; timestamp: string }> | null;
}

export interface Generation {
  id: number;
  condition_id: number;
  prompt_id: number;
  replicate_index: number;
  status: string;
  response_payload?: {
    content: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
  };
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  completed_at?: string;
}

export interface Prompt {
  id: number;
  chunk_id: number;
  category?: string;
  label?: string;
  context: Record<string, any>;
  metadata: Record<string, any>;
}

export interface ComparisonQueueItem {
  prompt: Prompt;
  condition_a: Condition;
  condition_b: Condition;
  generation_a: Generation;
  generation_b: Generation;
}

export interface ELORating {
  condition_id: number;
  condition: Condition;
  rating: number;
  games_played: number;
  last_updated: string;
}

export interface ComparisonCreate {
  prompt_id: number;
  condition_a_id: number;
  condition_b_id: number;
  winner_condition_id?: number;
  evaluator: string;
  notes?: string;
}

export interface GenerationRun {
  id: string;
  label?: string;
  started_at: string;
  completed_at?: string;
  total_generations: number;
  completed_generations: number;
  failed_generations: number;
}

export const auditionAPI = {
  /**
   * List all generation runs.
   */
  async getGenerationRuns(): Promise<GenerationRun[]> {
    const response = await fetch(`${API_BASE}/runs`);
    if (!response.ok) throw new Error('Failed to fetch generation runs');
    return response.json();
  },

  /**
   * Get the next pending comparison.
   */
  async getNextComparison(params?: {
    run_id?: string;
    condition_a_id?: number;
    condition_b_id?: number;
  }): Promise<ComparisonQueueItem | null> {
    const searchParams = new URLSearchParams();
    if (params?.run_id) searchParams.append('run_id', params.run_id);
    if (params?.condition_a_id) searchParams.append('condition_a_id', params.condition_a_id.toString());
    if (params?.condition_b_id) searchParams.append('condition_b_id', params.condition_b_id.toString());

    const response = await fetch(`${API_BASE}/comparisons/next?${searchParams}`);
    if (!response.ok) throw new Error('Failed to fetch comparison');
    return response.json();
  },

  /**
   * Record a comparison judgment.
   */
  async createComparison(comparison: ComparisonCreate): Promise<{
    id: number;
    created_at: string;
    elo_ratings: {
      condition_a: { rating: number; delta: number };
      condition_b: { rating: number; delta: number };
    };
  }> {
    const response = await fetch(`${API_BASE}/comparisons`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(comparison),
    });
    if (!response.ok) throw new Error('Failed to create comparison');
    return response.json();
  },

  /**
   * Get ELO leaderboard.
   */
  async getLeaderboard(limit = 10): Promise<ELORating[]> {
    const response = await fetch(`${API_BASE}/leaderboard?limit=${limit}`);
    if (!response.ok) throw new Error('Failed to fetch leaderboard');
    return response.json();
  },

  /**
   * Export a comparison to JSON.
   */
  async exportComparison(comparisonId: number): Promise<any> {
    const response = await fetch(`${API_BASE}/export/${comparisonId}`);
    if (!response.ok) throw new Error('Failed to export comparison');
    return response.json();
  },

  /**
   * Get count of missing generations that need regeneration.
   */
  async getMissingGenerationCount(): Promise<{ count: number }> {
    const response = await fetch(`${API_BASE}/generate/count`);
    if (!response.ok) throw new Error('Failed to fetch missing generation count');
    return response.json();
  },

  /**
   * Start a generation job.
   */
  async startGeneration(limit?: number, max_workers?: number): Promise<{ job_id: string; status: string }> {
    const params = new URLSearchParams();
    if (limit && limit > 0) params.append('limit', limit.toString());
    if (max_workers && max_workers > 0) params.append('max_workers', max_workers.toString());

    const url = params.toString()
      ? `${API_BASE}/generate/start?${params}`
      : `${API_BASE}/generate/start`;

    const response = await fetch(url, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Failed to start generation job');
    return response.json();
  },

  /**
   * Stop a generation job.
   */
  async stopGeneration(jobId: string): Promise<{ status: string; job_id: string }> {
    const response = await fetch(`${API_BASE}/generate/stop?job_id=${jobId}`, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Failed to stop generation job');
    return response.json();
  },

  /**
   * Get output and stats from a generation job.
   */
  async getGenerationOutput(jobId: string): Promise<{
    output: string;
    stats: { total: number; remaining: number; completed: number; failed: number } | null;
    status: string;
    job_id: string;
  }> {
    const response = await fetch(`${API_BASE}/generate/output?job_id=${jobId}`);
    if (!response.ok) throw new Error('Failed to fetch job output');
    return response.json();
  },

  /**
   * Import a context package JSON file and register it as a prompt.
   */
  async importPrompt(file: File): Promise<{
    success: boolean;
    chunk_id: number;
    prompt_id: number;
    message: string;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/import/prompt`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to import prompt');
    }
    return response.json();
  },
};
