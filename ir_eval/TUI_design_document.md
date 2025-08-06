# Software Design Document: NEXUS IR Evaluation Textual TUI

## 1. Executive Summary

This document outlines the design for a Text User Interface (TUI) built with the Textual library to provide a modernized interface for the NEXUS IR Evaluation System. The TUI will maintain the efficiency of CLI workflows while adding visual enhancements, improved navigation, and a more intuitive user experience. The design prioritizes minimal adaptation requirements for integration with the existing IR evaluation suite.

## 2. System Overview

### 2.1 Current Architecture

The NEXUS IR Evaluation System currently provides:
- A CLI-based interface (`ir_eval.py`)
- PostgreSQL database integration
- Query execution against the MEMNON retrieval system
- Result evaluation and judgment workflows
- Metrics calculation and comparison

### 2.2 Integration Points

The TUI will interface with the existing system at these key points:
- Database access via the `IRDatabasePG` class
- Query execution via the `run_golden_queries` function
- Judgment collection via the `PGQRELSManager`
- Results comparison via the `compare_runs` function

## 3. TUI Design

### 3.1 Core Principles

1. **Minimal backend changes**: The TUI should use existing APIs without requiring significant refactoring
2. **Keyboard-driven**: Preserve efficient keyboard navigation while adding mouse support
3. **Progressive enhancement**: Add visual elements without sacrificing performance
4. **Responsive design**: Adapt to different terminal sizes and resolutions
5. **State preservation**: Maintain session state across different views

### 3.2 Screen Architecture

The TUI will use a screen stack architecture with these primary screens:

1. **Main Dashboard**
   - Summary metrics
   - Recent runs
   - Quick navigation

2. **Query Execution**
   - Configuration selection (control/experimental)
   - Category filtering
   - Run configuration and parameters

3. **Judgment Interface**
   - Query context display
   - Document viewing with syntax highlighting
   - Relevance scoring controls
   - Progress tracking

4. **Results Comparison**
   - Side-by-side metrics visualization
   - Category-specific comparisons
   - Statistical significance indicators

5. **Settings Management**
   - Parameter configuration
   - Visual theme customization
   - Database connection management

### 3.3 Color Scheme

The TUI will use a consistent color scheme that enhances readability while maintaining a terminal aesthetic:

- **#39FF14 (Terminal Green)**: Default system color for primary content and general text
- **#61D6D6 (Bright Cyan)**: Headers, system messages, and section titles
- **#0037DA (Blue)**: User-entered text, interactive elements, and selected items

This color scheme should be implemented as a Textual CSS theme that can be easily applied across all screens and components.

## 4. Component Design

### 4.1 Dashboard Components

```
┌─ NEXUS IR Evaluation ─────────────────────────────────────────────┐
│                                                                    │
│  ┌─ System Status ───┐  ┌─ Recent Runs ────────────────────────┐  │
│  │ DB: Connected     │  │ ID  Name        Type        Time     │  │
│  │ Judgments: 1,245  │  │ 42  Exp_hybrid  Experiment  12:30 PM │  │
│  │ Queries: 86       │  │ 41  Control_std Control     12:28 PM │  │
│  └───────────────────┘  │ 38  Test_boost  Experiment  11:15 AM │  │
│                         │ 36  Control_std Control     11:13 AM │  │
│  ┌─ Quick Actions ───┐  └─────────────────────────────────────────┘
│  │ [R] Run Queries   │                                             │
│  │ [J] Judge Results │  ┌─ Performance Summary ──────────────────┐ │
│  │ [C] Compare Runs  │  │                                        │ │
│  │ [S] Settings      │  │  [Chart: Performance metrics by        │ │
│  │ [Q] Quit          │  │   category showing improvement]        │ │
│  └───────────────────┘  │                                        │ │
│                         └────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 Judgment Interface Components

```
┌─ Judgment Interface ──────────────────────────────────────────────┐
│ QUERY: Where is the Silo?                                         │
│ CATEGORY: location / NAME: desert_silo                            │
│                                                                    │
│ ┌─ Document 3/25 ─────────────────────────────────────────────┐   │
│ │                                                              │   │
│ │ The old missile silo had been abandoned since the end of     │   │
│ │ the Cold War. Nestled between two ridges in the desert,      │   │
│ │ it was nearly invisible unless you knew exactly where to     │   │
│ │ look. Alex had converted the underground bunker into a       │   │
│ │ home, reinforcing the structure and adding solar panels      │   │
│ │ on the ridge that powered his equipment.                     │   │
│ │                                                              │   │
│ │ [Highlighted terms: silo, desert]                            │   │
│ └──────────────────────────────────────────────────────────────┘   │
│                                                                    │
│ PROGRESS: 2/25 judged | 23 remaining for this query               │
│ TOTAL REMAINING: 142 documents left to judge                       │
│                                                                    │
│ ┌─ Relevance ──────────┐  ┌─ Actions ────────────────────────┐    │
│ │ [0] Irrelevant       │  │ [S] Skip Document                │    │
│ │ [1] Marginal         │  │ [U] Undo Last Judgment           │    │
│ │ [2] Relevant         │  │ [Q] Quit to Main Menu            │    │
│ │ [3] Highly Relevant  │  │ [H] Help                         │    │
│ └──────────────────────┘  └──────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

### 4.3 Results Comparison Components

```
┌─ Results Comparison ─────────────────────────────────────────────┐
│ Control: standard_retrieval   vs   Experiment: hybrid_search     │
│                                                                   │
│ ┌─ Overall Metrics ───────────────────────────────────────────┐   │
│ │ Metric    Control   Experiment   Diff     % Change   Better │   │
│ │ P@5       0.65      0.78         +0.13    +20.0%     Exp ✓  │   │
│ │ P@10      0.58      0.72         +0.14    +24.1%     Exp ✓  │   │
│ │ MRR       0.72      0.85         +0.13    +18.1%     Exp ✓  │   │
│ │ BPref     0.66      0.71         +0.05    +7.6%      Exp ✓  │   │
│ └─────────────────────────────────────────────────────────────┘   │
│                                                                   │
│ ┌─ Category: character ───────────────────────────────────────┐   │
│ │ [Bar chart comparing metrics between control/experiment]     │   │
│ └─────────────────────────────────────────────────────────────┘   │
│                                                                   │
│ ┌─ Query Analysis ────────────────────────────────────────────┐   │
│ │ Most improved queries:                                       │   │
│ │ 1. "Where is the Silo?" (+0.45 P@5)                         │   │
│ │ 2. "What happened to Morgan?" (+0.40 P@5)                   │   │
│ │                                                              │   │
│ │ [D] Detailed view  [P] Previous category  [N] Next category │   │
│ └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

## 5. Implementation Strategy

### 5.1 Architecture Overview

```
┌─────────────────┐      ┌────────────────┐     ┌─────────────────┐
│ Textual TUI     │      │ Controller     │     │ IR Eval System  │
│                 │◄────►│                │◄───►│                 │
│ - Screens       │      │ - API Adapter  │     │ - IRDatabasePG  │
│ - Widgets       │      │ - State Mgmt   │     │ - PGQRELSManager│
│ - Event Handlers│      │ - Data Format  │     │ - Module APIs   │
└─────────────────┘      └────────────────┘     └─────────────────┘
```

### 5.2 Core Classes

1. **IRApp**: Main Textual application class
   ```python
   class IRApp(App):
       """Main Textual application for IR Evaluation."""
       CSS_PATH = "ir_eval.tcss"
       SCREENS = {
           "dashboard": DashboardScreen,
           "run_queries": QueryScreen,
           "judgment": JudgmentScreen,
           "comparison": ComparisonScreen,
           "settings": SettingsScreen,
       }
   ```

2. **IRController**: Bridge between TUI and backend
   ```python
   class IRController:
       """Controller managing interaction between TUI and IR backend."""
       def __init__(self, db_path=None):
           self.db = IRDatabasePG(db_path)
           self.qrels = PGQRELSManager()
           
       async def run_queries(self, config_type, category=None, **kwargs):
           """Run queries and return results."""
           # Call existing run_golden_queries function
   ```

3. **JudgmentScreen**: Core judgment interface
   ```python
   class JudgmentScreen(Screen):
       """Screen for judging relevance of search results."""
       def compose(self) -> ComposeResult:
           """Compose the judgment screen layout."""
           yield Header(id="header")
           yield QueryInfo(id="query_info")
           yield DocumentViewer(id="document_viewer")
           yield Footer(id="footer")
       
       def on_key(self, event: events.Key) -> None:
           """Handle keyboard events."""
           if event.key == "0":
               self.judge_document(0)
           # ...etc
   ```

### 5.3 Key Widgets

1. **DocumentViewer**: Rich text display for result documents
2. **MetricsTable**: Interactive table for viewing metrics
3. **ComparisonChart**: Visual representation of performance metrics
4. **ProgressIndicator**: Visual indicator of judgment progress
5. **QuerySelector**: UI for selecting/filtering queries

### 5.4 CSS Styling

The TUI will use Textual CSS for styling, with a focus on the specified color scheme:

```css
/* Example CSS styling - to be expanded */
Screen {
    background: #000000;
    color: #39FF14;  /* Terminal Green for default text */
}

Header {
    background: #000000;
    color: #61D6D6;  /* Bright Cyan for headers */
    text-style: bold;
    height: 1;
}

Input {
    color: #0037DA;  /* Blue for user input */
}

.highlight {
    background: #0037DA;
    color: #FFFFFF;
}

.section-title {
    color: #61D6D6;
    text-style: bold;
}
```

## 6. Database Integration

### 6.1 Database Access Layer

The TUI will use the existing `IRDatabasePG` class for database access. No changes to the database schema are required.

### 6.2 Async Query Execution

To maintain responsiveness, long-running database operations will be executed asynchronously:

```python
@work(exclusive=True)
async def execute_query_run(self, settings_path, queries_path, config_type):
    """Run queries in background worker."""
    run_id = await run_golden_queries_async(
        settings_path, queries_path, config_type, db=self.db
    )
    self.post_message(QueryRunComplete(run_id=run_id))
```

## 7. File Structure

```
nexus_ir_tui/
├── __init__.py
├── app.py                # Main application entry point
├── controller.py         # Bridge to IR evaluation logic
├── ir_eval.tcss          # Textual CSS styling
├── screens/
│   ├── __init__.py
│   ├── dashboard.py      # Main dashboard screen
│   ├── judgment.py       # Judgment interface
│   ├── comparison.py     # Results comparison screen
│   ├── queries.py        # Query execution screen
│   └── settings.py       # Settings management screen
├── widgets/
│   ├── __init__.py
│   ├── document.py       # Document viewer widget
│   ├── metrics.py        # Metrics display widgets
│   ├── progress.py       # Progress tracking widgets
│   └── charts.py         # Data visualization widgets
└── utils/
    ├── __init__.py
    ├── async_db.py       # Async database helpers
    ├── formatters.py     # Text formatting utilities
    └── state.py          # Application state management
```

## 8. Configuration Management

The TUI will store configuration in a TOML file (`config.toml`) with these sections:

1. **Database**: Connection parameters
2. **UI**: Theme, colors, layout preferences
3. **Display**: Terminal-specific settings
4. **Keybindings**: Customizable keyboard shortcuts

Example configuration:

```toml
[database]
host = "localhost"
port = 5432
name = "NEXUS"
user = "pythagor"

[ui]
theme = "default"
primary_color = "#39FF14"  # Terminal Green
header_color = "#61D6D6"   # Bright Cyan
input_color = "#0037DA"    # Blue

[keybindings]
judge_0 = "0"
judge_1 = "1"
judge_2 = "2"
judge_3 = "3"
skip = "s"
undo = "u"
quit = "q"
```

## 9. Integration Strategy

### 9.1 Minimal Backend Changes

To minimize changes to the IR evaluation system:

1. Create thin wrapper functions with the same signatures as existing functions
2. Add async variants for long-running operations
3. Use the existing API contract without modifying core functionality

### 9.2 Implementation Phases

1. **Phase 1**: Core infrastructure and dashboard
2. **Phase 2**: Judgment interface
3. **Phase 3**: Run management and comparison tools
4. **Phase 4**: Settings and configuration
5. **Phase 5**: Visual enhancements and polish

## 10. Implementation Guidelines

### 10.1 Style Guide

- Follow Textual naming conventions for widgets and screens
- Use Python type annotations throughout
- Maintain separation between UI logic and IR system logic
- Document all public methods and classes

### 10.2 Error Handling

- Display errors in a dedicated modal dialog
- Log detailed errors to a rotating file logger
- Provide user-friendly error messages with recovery options

### 10.3 Testing Strategy

- Unit tests for controller logic
- Widget tests using Textual's testing utilities
- Integration tests for database operations
- End-to-end tests for complete workflows

## 11. Future Enhancements

- Real-time collaboration capabilities
- Custom reporting and export features
- Integrated data visualization
- Keyboard shortcut customization
- Theme selection and customization

## 12. Conclusion

This design provides a comprehensive blueprint for implementing a Textual-based TUI for the NEXUS IR Evaluation System. By following this design, Lovable can create a modern, responsive interface that enhances the user experience while requiring minimal adaptation of the existing IR evaluation codebase.

The specified color scheme of Terminal Green (#39FF14), Bright Cyan (#61D6D6), and Blue (#0037DA) provides a distinct visual language that balances readability with aesthetic appeal, maintaining the terminal feel while adding visual enhancements that improve usability.