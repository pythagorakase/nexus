---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- generated_from_trainer
- dataset_size:13536
- loss:TripletLoss
base_model: BAAI/bge-small-en-v1.5
widget:
- source_sentence: What is Alex-5?
  sentences:
  - 'Low-Impact Wired Reflexes ("Reflex Booster Lite" Mod)  Gives you enhanced reaction
    time without the full body-rig of a combat specialist. Improves speed in fights,
    dodging, quickdraws, and escaping danger. Keeps your movements natural-nothing
    too twitchy or robotic. End result: You''re faster, sharper, and harder to hit
    without looking unnatural.'
  - You skim past the usual offerings. Whiskey, rum, mezcal-predictable. Then-you
    spot something. A cocktail labeled "Driftlight." No real description. But the
    ingredients list a neuroactive component-one you recognize. Not full Verdant.
    Not a true Greenout. But close. A mild synesthetic enhancer. Something that tilts
    perception. Something that lets the mind stretch-softens the edges of thought
    without pulling you under. A tool for artists, for thinkers, for those seeking
    inspiration rather than oblivion.
  - No-Name Pete - Weird and dangerous, but if anyone can break the encryption, it's
    him.
- source_sentence: What is Alex's idea for launching a foundation?
  sentences:
  - 'Sam: "You ask where they are." A pause. Then-softer. "They are not here." A beat.
    "But I do not say they are gone." Another pause. "Only that they have not returned."
    A silence follows. Not because he is finished. But because he is choosing what
    to say next. And then-a final truth. "If they could return... they have not chosen
    to."'
  - 'You''re confusing generation with cognition. A proper digitized mind doesn''t
    just predict words-it thinks. It reacts. It evolves. It doesn''t just ''simulate''
    consciousness, it is consciousness. '
  - The doors swing open, and you step inside. The place is smaller, hotter, packed
    with the kind of people who came out tonight just to feel something. A tiny stage,
    glowing in cheap LED lights. A screen flashing lyrics, half a beat behind a singer
    who is absolutely butchering some ancient pop song. The crowd doesn't care. They're
    cheering, laughing, drinking like they've already forgotten tomorrow exists.
- source_sentence: How does crossing The Bridge work?
  sentences:
  - 'Sam: "You ask where they are." A pause. Then-softer. "They are not here." A beat.
    "But I do not say they are gone." Another pause. "Only that they have not returned."
    A silence follows. Not because he is finished. But because he is choosing what
    to say next. And then-a final truth. "If they could return... they have not chosen
    to."'
  - 'Note to AI: Using either dialog or narrative, include any description Nyati gives
    of her "eureka cure". Other elements of her debrief may be briefly paraphrased.'
  - The silence stretches. And you think you've outrun the thought- Until it catches
    up to you. It comes as a whisper, a shape at the edge of your mind. "You...could
    come with me." Even in your head, the words turn your stomach. You don't say them
    aloud. You don't dare.
- source_sentence: What happened to Victor Sato after Alex framed him?
  sentences:
  - Her chassis moves-deliberate, precise. The first slight shift in weight, the first
    motion of fingers, the first slow inhale. The body is no longer empty. The presence
    that has always surrounded you-your AI, your ship, your navigator, your anchor-now
    has a form. A center. And then-she opens her eyes. Not glass panels, not digitized
    optics. But eyes. Real. Focused.
  - So, you know I'm trans, more or less, obviously. I mean this isn't," Alex gestures
    broadly at herself, "an out of the box configuration. But my point is, I've already
    changed my body, pretty heavily. Maybe you'd recognize the old me, maybe not.
    I used to think that, because of that, I understood what you've been though. I
    was wrong. I get that now. Especially because, well, I never actually had any
    dysphoria. I didn't hate being a man at all. I was...indifferent to it. Like a
    coat that doesn't quite fit, but you get sort of used to it anyway. Then, when
    the opportunity came up, I was like, cool, an upgrade!
  - '"Recommended chassis model: Omniframe 8-Series, Variant ''Athena.'' Biomechanical
    framework optimized for fluid human interaction. Full sensory matrix. Adaptive
    kinetic response."'
- source_sentence: What was the result of the blacksite infiltration mission?
  sentences:
  - Dr. Nyati steps into a dimly lit bookshop café, the kind of place where the world
    slows down. The scent of old paper and fresh coffee settles around her as she
    trails a hand over book spines, feeling their weight. Something solid. Something
    known.
  - 'Alina: "...It is also within walking distance of Le Chat Noir, an establishment
    specializing in feline interaction and coffee." Pete immediately stops whatever
    he was doing. Pete: (slowly, pointing at Alina) "You absolute mastermind. You
    planned this." Nyati, already done with everything that is happening, just mutters-Nyati:
    "I cannot believe we''re aligning mission logistics around a cat café."'
  - Pete is still engaged. He hasn't bolted, hasn't backed out, hasn't overcorrected
    into pure panic mode.
pipeline_tag: sentence-similarity
library_name: sentence-transformers
metrics:
- pearson_cosine
- spearman_cosine
model-index:
- name: SentenceTransformer based on BAAI/bge-small-en-v1.5
  results:
  - task:
      type: semantic-similarity
      name: Semantic Similarity
    dataset:
      name: Unknown
      type: unknown
    metrics:
    - type: pearson_cosine
      value: .nan
      name: Pearson Cosine
    - type: spearman_cosine
      value: .nan
      name: Spearman Cosine
---

# SentenceTransformer based on BAAI/bge-small-en-v1.5

This is a [sentence-transformers](https://www.SBERT.net) model finetuned from [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5). It maps sentences & paragraphs to a 384-dimensional dense vector space and can be used for semantic textual similarity, semantic search, paraphrase mining, text classification, clustering, and more.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
- **Base model:** [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) <!-- at revision 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a -->
- **Maximum Sequence Length:** 512 tokens
- **Output Dimensionality:** 384 dimensions
- **Similarity Function:** Cosine Similarity
<!-- - **Training Dataset:** Unknown -->
<!-- - **Language:** Unknown -->
<!-- - **License:** Unknown -->

### Model Sources

- **Documentation:** [Sentence Transformers Documentation](https://sbert.net)
- **Repository:** [Sentence Transformers on GitHub](https://github.com/UKPLab/sentence-transformers)
- **Hugging Face:** [Sentence Transformers on Hugging Face](https://huggingface.co/models?library=sentence-transformers)

### Full Model Architecture

```
SentenceTransformer(
  (0): Transformer({'max_seq_length': 512, 'do_lower_case': True}) with Transformer model: BertModel 
  (1): Pooling({'word_embedding_dimension': 384, 'pooling_mode_cls_token': True, 'pooling_mode_mean_tokens': False, 'pooling_mode_max_tokens': False, 'pooling_mode_mean_sqrt_len_tokens': False, 'pooling_mode_weightedmean_tokens': False, 'pooling_mode_lasttoken': False, 'include_prompt': True})
  (2): Normalize()
)
```

## Usage

### Direct Usage (Sentence Transformers)

First install the Sentence Transformers library:

```bash
pip install -U sentence-transformers
```

Then you can load this model and run inference.
```python
from sentence_transformers import SentenceTransformer

# Download from the 🤗 Hub
model = SentenceTransformer("sentence_transformers_model_id")
# Run inference
sentences = [
    'What was the result of the blacksite infiltration mission?',
    'Dr. Nyati steps into a dimly lit bookshop café, the kind of place where the world slows down. The scent of old paper and fresh coffee settles around her as she trails a hand over book spines, feeling their weight. Something solid. Something known.',
    "Pete is still engaged. He hasn't bolted, hasn't backed out, hasn't overcorrected into pure panic mode.",
]
embeddings = model.encode(sentences)
print(embeddings.shape)
# [3, 384]

# Get the similarity scores for the embeddings
similarities = model.similarity(embeddings, embeddings)
print(similarities.shape)
# [3, 3]
```

<!--
### Direct Usage (Transformers)

<details><summary>Click to see the direct usage in Transformers</summary>

</details>
-->

<!--
### Downstream Usage (Sentence Transformers)

You can finetune this model on your own dataset.

<details><summary>Click to expand</summary>

</details>
-->

<!--
### Out-of-Scope Use

*List how the model may foreseeably be misused and address what users ought not to do with the model.*
-->

## Evaluation

### Metrics

#### Semantic Similarity

* Evaluated with [<code>EmbeddingSimilarityEvaluator</code>](https://sbert.net/docs/package_reference/sentence_transformer/evaluation.html#sentence_transformers.evaluation.EmbeddingSimilarityEvaluator)

| Metric              | Value   |
|:--------------------|:--------|
| pearson_cosine      | nan     |
| **spearman_cosine** | **nan** |

<!--
## Bias, Risks and Limitations

*What are the known or foreseeable issues stemming from this model? You could also flag here known failure cases or weaknesses of the model.*
-->

<!--
### Recommendations

*What are recommendations with respect to the foreseeable issues? For example, filtering explicit content.*
-->

## Training Details

### Training Dataset

#### Unnamed Dataset

* Size: 13,536 training samples
* Columns: <code>sentence_0</code>, <code>sentence_1</code>, and <code>sentence_2</code>
* Approximate statistics based on the first 1000 samples:
  |         | sentence_0                                                                       | sentence_1                                                                        | sentence_2                                                                         |
  |:--------|:---------------------------------------------------------------------------------|:----------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------|
  | type    | string                                                                           | string                                                                            | string                                                                             |
  | details | <ul><li>min: 6 tokens</li><li>mean: 11.9 tokens</li><li>max: 23 tokens</li></ul> | <ul><li>min: 4 tokens</li><li>mean: 68.8 tokens</li><li>max: 330 tokens</li></ul> | <ul><li>min: 5 tokens</li><li>mean: 55.38 tokens</li><li>max: 330 tokens</li></ul> |
* Samples:
  | sentence_0                                                                   | sentence_1                                                                                                                                                                                                            | sentence_2                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
  |:-----------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
  | <code>What does Vasquez look like?</code>                                    | <code>So I essentially just posited that he's an alien in a crashed spaceship, and his only correction seems to be a nitpick about whatever method of FTL travel they used-obviously with imperfect execution.</code> | <code>This oath is binding under honor and good faith, except in cases of gross misrepresentation, new evidence of catastrophic ethical breach, or subsequent escalation rendering prior restraint void.</code>                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
  | <code>Who or what is the being inside The Cradle?</code>                     | <code>IT IS A PAGE WITHOUT A BOOK. A CODE WITHOUT A MACHINE. A QUESTION WITHOUT AN ANSWER.</code>                                                                                                                     | <code>Primary Objective: Publicly frame your new version of Echo as a moral good-a clean break from the past.Secondary Objective: Buy back and rehabilitate failed Echo subjects-turn former corporate weapons into proof that your method works.Long-Term PR Value: Position yourself as the savior of digitized minds, not just their creator.KEY ELEMENTS OF THE FOUNDATION:  Nonprofit front-independent but heavily funded by your future corporate entity.  Run by a trusted figure-Emilia or Dr. Nyati. Someone with credibility, not just a corporate face.  Focused on "rehabilitation" of Echo victims-rescuing digital minds from unethical corporate use.  Used strategically to dismantle black-market Echo implementations-buy them out, rather than fight them.</code> |
  | <code>Where can the crew of the ghost observe the surrounding waters?</code> | <code>At some point, another rider pulls alongside her-Dr. Nyati, of all people, on a sleek black bike. They exchange glances, and without a word, the challenge is set. They race.</code>                            | <code>"So what's the play? Classy dining? Street food? Or are we eating whatever Alina finds the most *nutritionally efficient?"</code>                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
* Loss: [<code>TripletLoss</code>](https://sbert.net/docs/package_reference/sentence_transformer/losses.html#tripletloss) with these parameters:
  ```json
  {
      "distance_metric": "TripletDistanceMetric.EUCLIDEAN",
      "triplet_margin": 5
  }
  ```

### Training Hyperparameters
#### Non-Default Hyperparameters

- `eval_strategy`: steps
- `per_device_train_batch_size`: 64
- `per_device_eval_batch_size`: 64
- `num_train_epochs`: 5
- `multi_dataset_batch_sampler`: round_robin

#### All Hyperparameters
<details><summary>Click to expand</summary>

- `overwrite_output_dir`: False
- `do_predict`: False
- `eval_strategy`: steps
- `prediction_loss_only`: True
- `per_device_train_batch_size`: 64
- `per_device_eval_batch_size`: 64
- `per_gpu_train_batch_size`: None
- `per_gpu_eval_batch_size`: None
- `gradient_accumulation_steps`: 1
- `eval_accumulation_steps`: None
- `torch_empty_cache_steps`: None
- `learning_rate`: 5e-05
- `weight_decay`: 0.0
- `adam_beta1`: 0.9
- `adam_beta2`: 0.999
- `adam_epsilon`: 1e-08
- `max_grad_norm`: 1
- `num_train_epochs`: 5
- `max_steps`: -1
- `lr_scheduler_type`: linear
- `lr_scheduler_kwargs`: {}
- `warmup_ratio`: 0.0
- `warmup_steps`: 0
- `log_level`: passive
- `log_level_replica`: warning
- `log_on_each_node`: True
- `logging_nan_inf_filter`: True
- `save_safetensors`: True
- `save_on_each_node`: False
- `save_only_model`: False
- `restore_callback_states_from_checkpoint`: False
- `no_cuda`: False
- `use_cpu`: False
- `use_mps_device`: False
- `seed`: 42
- `data_seed`: None
- `jit_mode_eval`: False
- `use_ipex`: False
- `bf16`: False
- `fp16`: False
- `fp16_opt_level`: O1
- `half_precision_backend`: auto
- `bf16_full_eval`: False
- `fp16_full_eval`: False
- `tf32`: None
- `local_rank`: 0
- `ddp_backend`: None
- `tpu_num_cores`: None
- `tpu_metrics_debug`: False
- `debug`: []
- `dataloader_drop_last`: False
- `dataloader_num_workers`: 0
- `dataloader_prefetch_factor`: None
- `past_index`: -1
- `disable_tqdm`: False
- `remove_unused_columns`: True
- `label_names`: None
- `load_best_model_at_end`: False
- `ignore_data_skip`: False
- `fsdp`: []
- `fsdp_min_num_params`: 0
- `fsdp_config`: {'min_num_params': 0, 'xla': False, 'xla_fsdp_v2': False, 'xla_fsdp_grad_ckpt': False}
- `fsdp_transformer_layer_cls_to_wrap`: None
- `accelerator_config`: {'split_batches': False, 'dispatch_batches': None, 'even_batches': True, 'use_seedable_sampler': True, 'non_blocking': False, 'gradient_accumulation_kwargs': None}
- `deepspeed`: None
- `label_smoothing_factor`: 0.0
- `optim`: adamw_torch
- `optim_args`: None
- `adafactor`: False
- `group_by_length`: False
- `length_column_name`: length
- `ddp_find_unused_parameters`: None
- `ddp_bucket_cap_mb`: None
- `ddp_broadcast_buffers`: False
- `dataloader_pin_memory`: True
- `dataloader_persistent_workers`: False
- `skip_memory_metrics`: True
- `use_legacy_prediction_loop`: False
- `push_to_hub`: False
- `resume_from_checkpoint`: None
- `hub_model_id`: None
- `hub_strategy`: every_save
- `hub_private_repo`: None
- `hub_always_push`: False
- `gradient_checkpointing`: False
- `gradient_checkpointing_kwargs`: None
- `include_inputs_for_metrics`: False
- `include_for_metrics`: []
- `eval_do_concat_batches`: True
- `fp16_backend`: auto
- `push_to_hub_model_id`: None
- `push_to_hub_organization`: None
- `mp_parameters`: 
- `auto_find_batch_size`: False
- `full_determinism`: False
- `torchdynamo`: None
- `ray_scope`: last
- `ddp_timeout`: 1800
- `torch_compile`: False
- `torch_compile_backend`: None
- `torch_compile_mode`: None
- `dispatch_batches`: None
- `split_batches`: None
- `include_tokens_per_second`: False
- `include_num_input_tokens_seen`: False
- `neftune_noise_alpha`: None
- `optim_target_modules`: None
- `batch_eval_metrics`: False
- `eval_on_start`: False
- `use_liger_kernel`: False
- `eval_use_gather_object`: False
- `average_tokens_across_devices`: False
- `prompts`: None
- `batch_sampler`: batch_sampler
- `multi_dataset_batch_sampler`: round_robin

</details>

### Training Logs
| Epoch | Step | spearman_cosine |
|:-----:|:----:|:---------------:|
| 1.0   | 212  | nan             |


### Framework Versions
- Python: 3.9.6
- Sentence Transformers: 3.4.1
- Transformers: 4.49.0
- PyTorch: 2.6.0
- Accelerate: 1.5.2
- Datasets: 3.4.1
- Tokenizers: 0.21.0

## Citation

### BibTeX

#### Sentence Transformers
```bibtex
@inproceedings{reimers-2019-sentence-bert,
    title = "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks",
    author = "Reimers, Nils and Gurevych, Iryna",
    booktitle = "Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing",
    month = "11",
    year = "2019",
    publisher = "Association for Computational Linguistics",
    url = "https://arxiv.org/abs/1908.10084",
}
```

#### TripletLoss
```bibtex
@misc{hermans2017defense,
    title={In Defense of the Triplet Loss for Person Re-Identification},
    author={Alexander Hermans and Lucas Beyer and Bastian Leibe},
    year={2017},
    eprint={1703.07737},
    archivePrefix={arXiv},
    primaryClass={cs.CV}
}
```

<!--
## Glossary

*Clearly define terms in order to be accessible across audiences.*
-->

<!--
## Model Card Authors

*Lists the people who create the model card, providing recognition and accountability for the detailed work that goes into its construction.*
-->

<!--
## Model Card Contact

*Provides a way for people who have updates to the Model Card, suggestions, or questions, to contact the Model Card authors.*
-->