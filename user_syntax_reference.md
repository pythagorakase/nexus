# Git Commands

```
# Start New Branch
git checkout -b ai_experiment_branch

# Inspect Diffs Before Merging
git diff main ai_experiment_branch

# Reject Branch
git checkout main
git branch -D ai_experiment_branch

# Merge Branch
git checkout main
git merge ai_experiment_branch

# Recover from Disasters
git log --oneline  # Find the last good commit
git reset --hard <commit-hash>

# Or Revert Specific AI-Generated Commits
git revert <commit-hash>

# Link GitHub
git remote add origin https://github.com/pythagorakase/nexus.git

# Install Dependencies with Poetry
poetry install

# Stage Changes for Commit
git add . # Add all changes in the current directory
git add <file_path> # Add a specific file

# Commit Staged Changes
git commit -m "Your commit message here"

# Push Changes to Remote (GitHub)
git push origin <branch_name> # Usually 'main' or your feature branch
```

# PSQL Login

```
# Login using details from settings.json
psql -U pythagor -h localhost NEXUS

```


Submarine that serves as primary vessel and mobile base of operations for Alex and her crew. It is described as a self-sustaining, heavily modified submersible equipped with advanced systems, including a high-efficiency power cell with a projected operational lifespan of 172 years. Capable of deep-sea descent, stealth operation, and long-term habitation. Interior includes a bridge, gym, galley, private quarters, and a Nexus test lab, where the crew conducts various activities such as mission planning, personal interactions, and scientific experiments.

Equipped with advanced cybernetic and computational infrastructure, including a Nexus core for consciousness transfer experiments and a secure system for cognitive mirroring tests. Alina, an AI who was formerly human, inhabits both the ship’s systems and a humanoid chassis, and is able to monitor, control, and interact with all aspects of The Ghost’s operations. The ship is described as having a calm, steady hum, with dim lighting and a variety of digital interfaces and displays. It is also noted for its ability to maintain environmental stability and provide for the crew’s physical and psychological needs during extended missions.