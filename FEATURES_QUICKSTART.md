# Entities Graph UI - Quick Start Guide

This guide provides quick instructions for using the new features in the entities-graph visualization.

## Feature 1: Depth-based Node Selection

**What it does**: Automatically selects connected nodes when you click a node in selection mode.

**How to use**:
1. Click the "⬚ Select" button to enable selection mode
2. Choose your desired depth from the dropdown in the selection panel (0-3)
   - **0**: Only the clicked node
   - **1**: Clicked node + direct neighbors
   - **2**: Clicked node + neighbors up to 2 hops away
   - **3**: Clicked node + neighbors up to 3 hops away
3. Click any node to select it and all connected nodes up to the chosen depth

**Tip**: Start with depth 1 for most cases. Use higher depths for exploring densely connected subgraphs.

---

## Feature 2: Bulk Link All

**What it does**: Creates relationships between all pairs of selected nodes.

**How to use**:
1. Select 2 or more nodes (using selection mode)
2. Click the **"Link All"** button (purple) in the selection panel
3. Enter the relationship type when prompted (e.g., "colleague", "related_to")
4. Confirm and wait for the operation to complete

**Example**: Selecting 3 nodes (A, B, C) will create links: A↔B, A↔C, B↔C

---

## Feature 3: Bulk Merge Selected

**What it does**: Merges multiple entities into one.

**How to use**:
1. Select 2 or more nodes (the first selected will be kept)
2. Click the **"Merge Selected"** button (orange) in the selection panel
3. Confirm the merge operation
4. The graph will reload with merged entities

**Warning**: This operation is permanent and cannot be undone!

---

## Feature 4: Inline Entity Editing

**What it does**: Edit entity name and type directly in the detail modal.

**How to use**:
1. Click any entity node to open its detail modal
2. Click the **"Edit"** button (blue) in the modal header
3. Edit the name in the text field
4. Change the entity kind from the dropdown
5. Click **"Save"** to apply changes, or **"Cancel"** to discard

**Note**: Changes are visual only until the page is reloaded. Backend persistence requires additional API endpoints.

---

## Feature 5: Filter Management

### Adding New Filter Types

**How to use**:
1. Look for the small text inputs next to the filter pills
   - "**+ node type**" for entity types
   - "**+ edge type**" for relationship types
2. Type the new filter name and press Enter
3. The new filter will be added and automatically whitelisted

### Deleting Filter Types

**How to use**:
1. Find the filter pill you want to remove
2. Click the **✕** button next to the filter name
3. The filter will be removed from all filter sets

---

## Feature 6: Filter State Cycling

**What it does**: Cycle through filter states with a single button (no more right-click!).

**How to use**:
1. Click any filter pill repeatedly to cycle through states:
   
   **For Node Filters**:
   - **Default** (normal border) → Shows all nodes of this type
   - **Blacklist** (red border, strikethrough) → Hides nodes of this type
   - **Whitelist** (thick colored border) → Shows ONLY nodes of this type
   - **Pre-request** (extra-thick border, ⬆ icon) → Filters at API level
   - Back to **Default**
   
   **For Edge Filters**:
   - **Default** → **Blacklist** → **Whitelist** → **Default**

**Visual Cues**:
- **3px border**: Pre-request filter (affects API query)
- **2px colored border**: Whitelist (include only)
- **2px red border**: Blacklist (exclude)
- **1.5px border**: Default (no filter)

---

## Feature 7: Node Glow Effect

**What it does**: Selected nodes get a colored glow for better visibility.

**How to use**:
1. Ensure you're in **2D mode** (glow doesn't work in 3D)
2. Enter selection mode by clicking "⬚ Select"
3. Click nodes to select them
4. Selected nodes will display a radial glow matching their type color

**Note**: The glow effect is automatically color-matched to the node's entity type.

---

## Tips & Best Practices

### Selection Workflow
1. **Start simple**: Use depth 0-1 for most selections
2. **Preview first**: Check the selection count before bulk operations
3. **Use Clear button**: Reset selections between different operations

### Filter Workflow
1. **Start broad**: Begin with default filters, then narrow down
2. **Use pre-request**: For large datasets, use pre-request filters to reduce API load
3. **Combine types**: Mix node and edge filters for precise results

### Bulk Operations
1. **Small batches**: Start with 2-5 nodes to test
2. **Verify first**: Check selected nodes before merging
3. **Backup important data**: Merge operations are permanent

### Performance
- **Large graphs**: Use depth 0-1 to avoid selecting too many nodes
- **Many filters**: Delete unused filter types to keep the UI clean
- **Slow operations**: Bulk operations are sequential—be patient with many nodes

---

## Keyboard Shortcuts

Currently, there are no dedicated keyboard shortcuts. Future versions may include:
- `Shift+Click` for multi-select without selection mode
- `Ctrl+A` to select all visible nodes
- `Escape` to clear selection
- `Ctrl+Z` to undo bulk operations

---

## Troubleshooting

**Q: Selection depth isn't working**  
A: Ensure you're in selection mode (⬚ Select button is highlighted)

**Q: Edit button doesn't appear**  
A: Edit is only available for entity nodes (not page/image/seed/media types)

**Q: Glow effect not visible**  
A: Switch to 2D mode (glow only works in 2D, not 3D)

**Q: Filter search not working**  
A: Type the exact filter name and press Enter to add it

**Q: Bulk operation failed**  
A: Check the browser console for API errors. Ensure you have proper permissions.

---

## Browser Compatibility

All features require:
- Modern browser (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- JavaScript enabled
- Canvas API support (for glow effect)

For best experience, use the latest version of Chrome or Firefox.

---

## Need Help?

- Check `ENTITIES_GRAPH_CHANGES.md` for technical details
- Check `IMPLEMENTATION_SUMMARY.md` for feature overview
- Report issues on the project's GitHub repository
