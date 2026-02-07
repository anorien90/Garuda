# Deep RAG Graph Exploration - Usage Examples and Test Scenarios

## Test Scenario 1: Semantic Entity Search

### Setup
- Ensure you have entities in your database (e.g., "Microsoft Corporation", "Bill Gates", "Satya Nadella")
- Navigate to the Graph tab in the Web UI

### Steps
1. In the "Deep RAG Graph Exploration" section, locate the "Semantic Entity Search" input
2. Type "microsoft" in the search box
3. Keep the default threshold at 0.7
4. Click the "Search" button

### Expected Results
- A modal window appears showing search results
- Results include both exact matches (e.g., "Microsoft Corporation") with score 1.0
- Results may include semantic matches (e.g., "Microsoft Azure") with scores 0.7-0.99
- Each result shows:
  - Entity name
  - Entity type/kind
  - Match type (Exact or Semantic)
  - Similarity score percentage
- Matching entities are highlighted in red in the graph visualization

### Variations
- Try searching with a threshold of 0.85 for stricter matching
- Search for partial names like "micro" or "corp"
- Search for entity types like "ceo" or "executive"

## Test Scenario 2: Graph Traversal

### Setup
- Load a graph with interconnected entities
- Example: A company with employees, products, and locations

### Steps
1. Click on any entity node in the graph (e.g., "Microsoft Corporation")
2. Observe that the "Traverse from Selected" button becomes enabled
3. Set "Max Depth" to 2
4. Set "Top N" to 10
5. Click "Traverse from Selected"

### Expected Results
- A modal window displays traversal results organized by depth
- **Depth 0** (Starting): Shows the selected entity
- **Depth 1**: Shows up to 10 directly connected entities (e.g., employees, products, headquarters)
- **Depth 2**: Shows up to 10 entities connected to depth 1 entities
- Each depth level shows:
  - Entity names
  - Relationship types (e.g., "works_for", "located_in")
  - Direction (incoming/outgoing)
  - Connection count
- The graph may update to include newly discovered entities
- Status message shows how many nodes and links were added

### Variations
- Try different max depth values (1-5)
- Adjust Top N to see more or fewer entities per level
- Start from different entity types (person, organization, location)

## Test Scenario 3: Path Finding

### Setup
- Ensure you have entities with relationship chains
- Example: Person → Company → Product → Location

### Steps
1. **Select First Node**:
   - Hold Shift key
   - Click on an entity node (e.g., "Bill Gates")
   - Observe the path status updates to "Selected 1 node"
   
2. **Select Second Node**:
   - Continue holding Shift
   - Click on another entity node (e.g., "Windows")
   - Observe the "Find Path" button becomes enabled
   - Status shows "Ready to find path between 2 nodes"

3. **Find Path**:
   - Click the "Find Path" button

### Expected Results
- A modal window displays the path results
- If a path exists:
  - Shows "Path Found" with path length
  - Lists all entities in the path from source to target
  - Shows relationship types connecting each pair
  - Highlights the path in green in the graph
  - Example path: Bill Gates → (founder) → Microsoft → (created) → Windows
- If no path exists:
  - Shows "No path found" message
  - Indicates the entities are not connected within the max depth

### Variations
- Try finding paths between entities in the same domain
- Attempt to find paths between unrelated entities
- Test with entities at different depths in the graph

## Test Scenario 4: Combined Workflow

### Real-World Use Case: Investigating Company Connections

1. **Initial Search**:
   - Use semantic search to find "technology companies"
   - Review all matching entities

2. **Select Anchor Entity**:
   - Click on the most relevant company (e.g., "Apple Inc.")

3. **Explore Relationships**:
   - Use graph traversal with depth=3 to discover:
     - Executives and employees
     - Products and services
     - Locations and facilities
     - Partner companies

4. **Find Hidden Connections**:
   - Use Shift+Click to select two seemingly unrelated entities
   - Use path finding to discover how they're connected
   - Example: Find path from "Tim Cook" to "iPhone"

5. **Refine View**:
   - Use node/edge filters to focus on specific entity types
   - Adjust depth to control visualization complexity

## Test Scenario 5: Multi-Modal Search

### Combining Search Methods

1. **Start with Semantic Search**:
   - Search for "artificial intelligence companies"
   - Identify 3-5 key entities

2. **Traverse Each Entity**:
   - For each found entity:
     - Click to select
     - Traverse with depth=2, top_n=5
     - Note the related entities

3. **Find Cross-Connections**:
   - Select two entities from different search results
   - Use path finding to see if they share connections

4. **Build Knowledge Map**:
   - Document the discovered network structure
   - Identify key hub entities (high connection count)
   - Note relationship types and patterns

## Edge Cases and Error Handling

### Test Case: No Matching Entities
- Search with very specific query that doesn't match
- Expected: Modal shows "No entities found"
- UI remains responsive

### Test Case: Isolated Entity
- Select an entity with no relationships
- Attempt traversal
- Expected: Results show only the root entity
- Message indicates no connections found

### Test Case: No Path Exists
- Select two entities in separate graph components
- Attempt path finding
- Expected: "No path found" message
- Explanation provided

### Test Case: Large Result Sets
- Search with very general query (e.g., "company")
- Expected: Results limited to configured maximum (20 by default)
- Pagination or "show more" options available

## Performance Testing

### Small Graph (< 100 entities)
- All operations should complete in < 1 second
- UI should remain responsive
- No noticeable lag

### Medium Graph (100-1000 entities)
- Semantic search: 1-3 seconds
- Graph traversal depth=2: 1-2 seconds
- Path finding: 1-3 seconds
- UI may show loading indicators

### Large Graph (> 1000 entities)
- Semantic search: 2-5 seconds
- Graph traversal depth=3: 3-10 seconds
- Path finding: 2-10 seconds depending on distance
- Loading indicators should be clearly visible

## Accessibility Testing

1. **Keyboard Navigation**:
   - Tab through all controls
   - Enter key triggers search
   - Escape key closes modals

2. **Screen Reader**:
   - All buttons have descriptive labels
   - Status messages are announced
   - Results are navigable

3. **Visual Indicators**:
   - Disabled buttons are clearly distinguished
   - Selected nodes show visual feedback
   - Paths and highlights use sufficient contrast

## Browser Compatibility

Test in the following browsers:
- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest, macOS/iOS)

Expected: All features work identically across browsers.

## Common Issues and Solutions

### Issue: Traverse button stays disabled
**Solution**: Ensure you've clicked directly on a node, not on empty space

### Issue: Search returns no results
**Solution**: 
- Lower the similarity threshold
- Check that entities exist in database
- Verify embeddings are generated

### Issue: Graph becomes cluttered
**Solution**:
- Use filters to hide unwanted node/edge types
- Reload graph to reset
- Reduce Top N parameter for traversal

### Issue: Path highlighting not visible
**Solution**:
- Ensure both nodes are in the current graph view
- Check that the path was successfully found
- Try toggling between 2D and 3D views

## Integration Testing

### Test with Real Data
1. Load sample dataset (e.g., technology companies)
2. Perform all operations in sequence
3. Verify data integrity maintained
4. Check that no duplicate entities created

### Test with Empty Database
1. Start with no entities
2. Attempt all operations
3. Verify graceful error handling
4. Confirm helpful error messages

### Test after Data Updates
1. Perform traversal
2. Add new relationships via API
3. Repeat traversal
4. Verify new relationships appear

## Automated Testing Checklist

- [ ] Unit tests for graph search functions
- [ ] Integration tests for API endpoints
- [ ] UI component rendering tests
- [ ] End-to-end workflow tests
- [ ] Performance benchmarks
- [ ] Accessibility audit
- [ ] Cross-browser compatibility
- [ ] Mobile responsiveness
- [ ] Error handling coverage
- [ ] Data integrity validation
