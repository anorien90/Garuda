# Entities Graph UI Enhancements

This document summarizes the changes made to the entities-graph visualization UI.

## Files Modified

1. `/home/runner/work/Garuda/Garuda/src/garuda_intel/webapp/static/entities-graph.js`
2. `/home/runner/work/Garuda/Garuda/src/garuda_intel/webapp/templates/components/entities-graph.html`

## Changes Implemented

### 1. Depth-based Connected Node Selection

**Location**: `entities-graph.js` lines 79, 1585-1635

**Description**: When selecting a node in selection mode, the system can now automatically select all connected nodes up to a configurable depth.

**Features**:
- Added `selectionDepth` state variable (default: 0)
- Modified `toggleNodeSelection()` to use BFS (Breadth-First Search) to find all connected nodes within the specified depth
- Builds adjacency map from `filteredLinks` for efficient neighbor lookup
- Only applies depth expansion when selecting (not when deselecting)

**UI**: Added depth selector dropdown in the selection panel (0, 1, 2, 3 hops)

### 2. Bulk Link and Merge Operations

**Location**: `entities-graph.js` lines 1723-1804, HTML lines 68-69

**Description**: Added two new bulk operations for selected nodes.

**Features**:

#### Link All (`linkAllSelected()`)
- Links all selected nodes to each other with a user-specified relation type
- Prompts user for relation type
- Creates relationships for each pair (i × j combinations)
- POSTs to `/api/relationships/record` for each pair
- Shows success count and reloads graph

#### Merge Selected (`mergeSelectedNodes()`)
- Merges all selected nodes into the first selected node
- Prompts for confirmation
- POSTs to `/api/entities/{source_id}/merge/{target_id}` for each merge
- Shows success count and reloads graph

**UI**: Added "Link All" (purple) and "Merge Selected" (orange) buttons in selection panel

### 3. Inline Entity Editing in Detail Modals

**Location**: `entities-graph.js` lines 1082-1087, 1224-1288

**Description**: Enables editing entity name and kind directly in the detail modal.

**Features**:
- Added "Edit" button to entity node modals (only for entity types, not page/image/seed/media)
- Toggles display between view mode and edit mode
- Edit form includes:
  - Text input for entity name
  - Dropdown select for entity kind (populated from `allDbNodeKinds`)
  - Save and Cancel buttons
- Saves changes to local graph data (both `filteredNodes` and `currentNodes`)
- Updates modal title and re-renders graph with new data
- Changes persist in UI until page reload (visual-only editing)

**Note**: Changes are local to the frontend visualization. To persist to backend, additional API endpoints would be needed.

### 4. Delete Options for Filter Pills

**Location**: `entities-graph.js` lines 263-264, 293, 340-357

**Description**: Added delete functionality to filter pills.

**Features**:
- Added ✕ button to each filter pill (node and edge types)
- `_onFilterPillDelete()` handler removes the kind from:
  - `nodeWhitelist` / `edgeWhitelist`
  - `nodeBlacklist` / `edgeBlacklist`
  - `preRequestNodeFilters` (for nodes)
  - `allDbNodeKinds` / `allDbEdgeKinds`
- Re-renders after deletion
- Also added to relation filter pills

### 5. Search to Add Filter Types

**Location**: `entities-graph.js` lines 254-255, 268-272, 359-377

**Description**: Added search inputs to add new filter types.

**Features**:
- Added search input fields for both node and edge filters
- Inputs styled consistently with filter bar
- `_onFilterSearch()` handler:
  - Checks if entered type exists in known kinds
  - If new, adds to `allDbNodeKinds` or `allDbEdgeKinds`
  - Automatically whitelists the new kind
  - Re-renders filter bar

**UI**: Text inputs with placeholders "+ node type" and "+ edge type"

### 6. Replace Right-Click with Strong Border State

**Location**: `entities-graph.js` lines 273-338, HTML line 30

**Description**: Changed filter pill interaction from right-click to click-cycle with visual states.

**Features**:
- Removed `contextmenu` event listener for right-click
- Modified `_onFilterPillClick()` to cycle through states:
  - **Node filters**: default → blacklist → whitelist → pre-request → default
  - **Edge filters**: default → blacklist → whitelist → default
- Updated `_filterPill()` styling:
  - Pre-request state: 3px solid border with kind color (was 2px)
  - Whitelist state: 2px solid border with kind color
  - Blacklist state: 2px solid red border
  - Default state: 1.5px solid border with kind color
- Updated tooltip text to reflect new interaction
- Updated hint text in advanced panel

### 7. Colored Backdrop Blur for Selected Nodes

**Location**: `entities-graph.js` lines 2007-2029

**Description**: Added custom node rendering with glow effect for selected nodes in 2D mode.

**Features**:
- Added `nodeCanvasObject()` custom renderer (2D only)
- For selected nodes:
  - Draws radial gradient glow behind the node
  - Glow uses node color with reduced opacity (0.4 → 0)
  - Glow radius is 2.5x node size
- Then draws the normal node circle on top
- Only applies in 2D mode (3D uses default rendering)

## Summary of New State Variables

- `selectionDepth`: Number (0-3), controls how many hops to select when clicking a node

## Summary of New Functions

- `_onFilterPillDelete(e)`: Removes a filter type from all filter sets
- `_onFilterSearch(query, group)`: Adds a new filter type from search input
- `linkAllSelected()`: Creates relationships between all pairs of selected nodes
- `mergeSelectedNodes()`: Merges all selected nodes into the first one
- `_wireEditButtons(node)`: Wires up edit functionality in entity modals

## Modified Functions

- `renderFilterBar()`: Added search inputs, delete button event listeners
- `renderRelationFilterBar()`: Added delete buttons to relation pills
- `_filterPill()`: Added delete button, updated styling for pre-request state
- `_onFilterPillClick()`: Changed to cycle through states instead of toggle
- `toggleNodeSelection()`: Added depth-based BFS selection
- `renderNodeModalContent()`: Added edit button and edit form to entity modals
- `openNodeModal()`: Added call to `_wireEditButtons()`
- `renderGraph()`: Added custom `nodeCanvasObject()` for 2D glow effect
- `initEntitiesGraph()`: Wired up new button event listeners

## HTML Template Changes

**File**: `entities-graph.html`

1. **Selection Panel** (lines 50-70):
   - Added depth selector dropdown
   - Added "Link All" button
   - Added "Merge Selected" button

2. **Advanced Panel** (line 30):
   - Updated hint text for new filter interaction

## Testing Recommendations

1. Test depth-based selection with different depth values (0-3)
2. Test bulk link creation with multiple selected nodes
3. Test bulk merge with 2+ selected nodes
4. Test inline editing of entity name and kind
5. Test filter pill deletion
6. Test adding new filter types via search
7. Test filter state cycling (especially pre-request state)
8. Test node glow rendering in 2D mode
9. Verify all operations work correctly in both 2D and 3D modes
10. Test with different entity types (person, org, location, etc.)

## Browser Compatibility

- All features use standard JavaScript ES6+ syntax
- Custom canvas rendering requires Canvas API support (all modern browsers)
- Radial gradients used for glow effect (widely supported)

## Performance Considerations

- BFS selection with depth is O(V + E) where V = vertices, E = edges
- Bulk operations make sequential API calls (not parallelized)
- Custom node rendering adds minimal overhead in 2D mode
- Filter search is case-insensitive with simple string matching

## Known Limitations

1. Inline entity editing only updates local graph data (not persisted to backend without additional API endpoints)
2. Bulk operations don't batch API calls (sequential for error handling)
3. Filter search adds exact match only (no fuzzy matching or suggestions)
4. Node glow only works in 2D mode (3D uses default rendering)

## Future Enhancements

Consider adding:
- Persistent entity editing via PATCH endpoint
- Batched API calls for bulk operations
- Autocomplete suggestions for filter search
- 3D glow effect using custom materials
- Undo/redo functionality for bulk operations
