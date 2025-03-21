---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- generated_from_trainer
- dataset_size:90
- loss:TripletLoss
base_model: BAAI/bge-small-en-v1.5
widget:
- source_sentence: How did Alex support Nyati after the Eureka incident?
  sentences:
  - Dr. Nyati steps into a dimly lit bookshop café, the kind of place where the world
    slows down. The scent of old paper and fresh coffee settles around her as she
    trails a hand over book spines, feeling their weight. Something solid. Something
    known.
  - She is distant in her own way, but not unkind. If anything, she has been more
    open with you than with most-not because she needs to be, but because she chooses
    to be. There is respect there, a kind of understanding that runs deep. But it
    has never felt personal.
  - 'Alex: "It''s... that''s... can I... hug you?"Nyati stares for half a second too
    long.Then-exhales, shifting slightly under the sheets.  Nyati (hoarse, awkward,
    but not rejecting): Uh. Yeah. Sure.'
- source_sentence: Why did Alex's performance cause so much unexpected emotional turmoil?
  sentences:
  - 'She is staring at you. Not like the others. Not in awe. Not in shock. But in
    something deeper, heavier. Something smoldering, something trying not to consume
    itself. She is not blushing-because she has passed the point of blushing. She
    is holding onto control by a thread. And you? You just sit there. Letting it hang.
    Letting her feel every moment of it. Then-after a long, long pause-she leans in,
    just slightly. Not touching you. Just close enough that you feel the warmth of
    her body, the ghost of breath against your skin. And-with a voice low, even, but
    carrying the weight of everything she is barely keeping contained-she says, simply:
    "You''re playing a dangerous game."  '
  - The reactor hums like a living thing, encased in reinforced shielding, cables
    thick as a man's arm feeding its power into Nexus's hungry core. Diagnostic panels
    glow faintly, cycling through their readouts-heat distribution, coolant pressure,
    energy draw. An old, scratched-up maintenance panel is welded shut-whoever owned
    this boat before you made field repairs the hard way. A faint, rhythmic vibration
    runs through the deck plating-the deep, slow heartbeat of a ship built to endure.
  - Her chassis moves-deliberate, precise. The first slight shift in weight, the first
    motion of fingers, the first slow inhale. The body is no longer empty. The presence
    that has always surrounded you-your AI, your ship, your navigator, your anchor-now
    has a form. A center. And then-she opens her eyes. Not glass panels, not digitized
    optics. But eyes. Real. Focused.
- source_sentence: What was the result of the blacksite infiltration mission?
  sentences:
  - He was a builder. He was many. He was part of something vast. Not an individual.
    A collective. A node in a greater whole. His task was to create-to shape the foundation,
    to weave the connections. Then-fracture. Something broke. Not in the structure,
    but in the mind. In the unity. He was... removed. Or he removed himself.
  - Ghost tours will remain a low-priority engagement, unless strategic conditions
    indicate otherwise.
  - '"I think we need to strike a sensible balance between..." A pause. A very deliberate
    pause. Then-you turn to Pete, your expression shifting from neutral to something
    just slightly wicked. A smile that promises suffering. "...Best Buy Geek Squad."
    Pete, deeply insulted, hand over heart: "I AM SO MUCH COOLER THAN THAT." You continue,
    undeterred. Raising a finger as if guiding a panel through a high-stakes corporate
    presentation. "And..." A pause. A slow exhale, like you are drawing from a deep
    well of wisdom. Then-calmly, with the absolute precision of a perfect takedown:
    "That kind of guy that lives out fantasies of being tactical-adjacent by buying
    his pants from 5.11-" Nyati immediately chokes on laughter. Pete, horrified: "DON''T
    YOU DARE SAY IT-" You, finishing the execution with ease: "Only to end up as viral
    post-fodder on r/iamverybadass."'
- source_sentence: What is the Land Rig?
  sentences:
  - Alex and Emilia step into the briefing area, where the rest of the crew has already
    started final prep.
  - 'She is staring at you. Not like the others. Not in awe. Not in shock. But in
    something deeper, heavier. Something smoldering, something trying not to consume
    itself. She is not blushing-because she has passed the point of blushing. She
    is holding onto control by a thread. And you? You just sit there. Letting it hang.
    Letting her feel every moment of it. Then-after a long, long pause-she leans in,
    just slightly. Not touching you. Just close enough that you feel the warmth of
    her body, the ghost of breath against your skin. And-with a voice low, even, but
    carrying the weight of everything she is barely keeping contained-she says, simply:
    "You''re playing a dangerous game."  '
  - '"As a friend? Just don''t disappear again." A pause. Then, almost as an afterthought:
    "That sucked."'
- source_sentence: How did Emilia react to Alex's karaoke performance?
  sentences:
  - '"Lab coat is too easy." A pause. Then-her eyes flick toward you, just briefly.
    "But the structured tailoring works." Pete, delighted. "Ohhh, she''s invested
    now." Emilia, ignoring him. Instead-she picks a piece from a nearby rack. Examines
    it. A long, structured coat, but not a lab coat. Something with weight. Something
    that speaks to precision, to competency, to controlled authority. Then-calmly,
    turning toward Nyati, holding it up for judgment: "This." Nyati, narrowing her
    eyes, taking the coat from Emilia''s hands. "...It''s not bad."'
  - '"I haven''t had a cat in years!" Your voice comes out far too excited for the
    current conversation trajectory.'
  - THE GHOST - A SUBMERSIBLE MONASTERYThis is no military sub-no torpedo bays, no
    weapon systems. The corridors are tight, but not claustrophobic-built for endurance,
    not battle. Everything is designed for efficiency and longevity, not comfort.
    Alex moves through the halls, boots tapping against steel grates. Red emergency
    lighting pulses faintly in some corners, a low heartbeat. Coolant pipes snake
    along the ceiling, carrying the lifeblood of the reactor.
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
    "How did Emilia react to Alex's karaoke performance?",
    'THE GHOST - A SUBMERSIBLE MONASTERYThis is no military sub-no torpedo bays, no weapon systems. The corridors are tight, but not claustrophobic-built for endurance, not battle. Everything is designed for efficiency and longevity, not comfort. Alex moves through the halls, boots tapping against steel grates. Red emergency lighting pulses faintly in some corners, a low heartbeat. Coolant pipes snake along the ceiling, carrying the lifeblood of the reactor.',
    '"I haven\'t had a cat in years!" Your voice comes out far too excited for the current conversation trajectory.',
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

* Size: 90 training samples
* Columns: <code>sentence_0</code>, <code>sentence_1</code>, and <code>sentence_2</code>
* Approximate statistics based on the first 90 samples:
  |         | sentence_0                                                                        | sentence_1                                                                          | sentence_2                                                                         |
  |:--------|:----------------------------------------------------------------------------------|:------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------|
  | type    | string                                                                            | string                                                                              | string                                                                             |
  | details | <ul><li>min: 6 tokens</li><li>mean: 11.73 tokens</li><li>max: 21 tokens</li></ul> | <ul><li>min: 14 tokens</li><li>mean: 84.69 tokens</li><li>max: 330 tokens</li></ul> | <ul><li>min: 5 tokens</li><li>mean: 54.83 tokens</li><li>max: 159 tokens</li></ul> |
* Samples:
  | sentence_0                                 | sentence_1                                                                                                                                                                                                                                                                                                                               | sentence_2                                                                                                                                                                                             |
  |:-------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
  | <code>What does Nyati look like?</code>    | <code>You're a Dynacorp operative, a sleek, sharp-dressed predator in the corporate jungle. Your life is a high-stakes power play, navigating boardroom betrayals and back-alley executions with equal finesse. You sell dreams by day and nightmares by night, moving assets-both digital and human-like pieces on a chessboard.</code> | <code> I could temporarily take control of Jobbing Captain Nyati until Alex recovers. Like that beautiful chapter of Last of Us 1 where Ellie suddenly has to take control and look after Joel.</code> |
  | <code>What does Nyati look like?</code>    | <code>Your mind races. Dr. Alina Voss. The missing scientist. The one you were sent to find. The one whose research started this whole goddamn mess. And now she's... what? A file? A ghost? A mind buried in an encrypted tomb?</code>                                                                                                  | <code>That all makes sense, and I like the Jobbing Captain Nyati approach</code>                                                                                                                       |
  | <code>What is the bougie mall like?</code> | <code>Le Chat Noir offers a full café menu, including pastries, small plates, and select regional dishes. Their beignets have a 94% approval rating across independent review aggregators.</code>                                                                                                                                        | <code>Nyati to Emilia: Her gaze hardens. "You are her anchor." A pause. "Anchor the hell out of her. Buy us time."</code>                                                                              |
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
- `num_train_epochs`: 1
- `multi_dataset_batch_sampler`: round_robin

#### All Hyperparameters
<details><summary>Click to expand</summary>

- `overwrite_output_dir`: False
- `do_predict`: False
- `eval_strategy`: steps
- `prediction_loss_only`: True
- `per_device_train_batch_size`: 8
- `per_device_eval_batch_size`: 8
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
- `num_train_epochs`: 1
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
| 1.0   | 12   | nan             |


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