# SQLAlchemy Alias Fix Documentation

## Issue
SQLAlchemy was generating a deprecation warning when joining `Page` and `PageContent` entities:

```
SAWarning: An alias is being generated automatically against joined entity 
Mapper[PageContent(page_content)] due to overlapping tables. This is a legacy 
pattern which may be deprecated in a later release. Use the aliased() construct 
explicitly.
```

## Root Cause

Both `Page` and `PageContent` inherit from `BasicDataEntry` using SQLAlchemy's joined table inheritance (polymorphic inheritance):

```python
class BasicDataEntry(Base):
    __tablename__ = "entries"
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    entry_type: Mapped[str] = mapped_column(String, nullable=False)
    # ...

class Page(BasicDataEntry):
    __tablename__ = "pages"
    id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("entries.id"), primary_key=True)
    # ...

class PageContent(BasicDataEntry):
    __tablename__ = "page_content"
    id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("entries.id"), primary_key=True)
    # ...
```

When joining these two entities, SQLAlchemy must navigate through the shared `entries` table, creating overlapping table references. This triggers automatic alias generation, which is a legacy pattern that SQLAlchemy may deprecate in future versions.

## Solution

Use the `aliased()` function explicitly to create an alias for `PageContent` before joining:

```python
from sqlalchemy.orm import aliased

# Create explicit alias
page_content_alias = aliased(PageContent)

# Use the alias in the query
stmt = (
    select(Page.url, page_content_alias.text)
    .join(page_content_alias, Page.id == page_content_alias.page_id)
    .where(page_content_alias.text.ilike(keyword))
)
```

## Implementation Details

**File**: `src/garuda_intel/database/engine.py`  
**Method**: `search_intel()`  
**Lines**: 372-390

### Changes Made:
1. Created explicit alias: `page_content_alias = aliased(PageContent)`
2. Replaced all `PageContent` references with `page_content_alias` in:
   - Column selections (`page_content_alias.text`)
   - Join conditions (`Page.id == page_content_alias.page_id`)
   - Where clauses (`page_content_alias.text.ilike(kw_like)`)

### Why This Works:
- The `aliased()` function creates an explicit alias that SQLAlchemy recognizes
- This prevents automatic alias generation since we're providing one explicitly
- The query behavior remains identical (explicit alias = automatic alias in functionality)
- Prepares the code for future SQLAlchemy versions where automatic aliasing may be removed

## Testing

The fix was verified with comprehensive tests:

1. **Warning Detection Test**: Confirmed no SAWarning is generated
2. **Functionality Tests**: 
   - Basic keyword search
   - Entity type filtering  
   - Page type filtering
   - Snippet extraction
   - Result ordering

All tests passed successfully with real data.

## Best Practices

When joining entities that share a common parent in polymorphic inheritance:

1. **Always use explicit `aliased()`** for clarity and to avoid deprecation warnings
2. **Add comments** explaining why the alias is needed
3. **Use descriptive alias names** (e.g., `page_content_alias` instead of `pc`)
4. **Be consistent** - if one entity needs an alias due to inheritance, use aliases for all similar patterns

## Future Considerations

If you encounter similar warnings with other entity joins:

1. Check if the entities inherit from the same base class
2. Look for joined table inheritance patterns
3. Apply the same `aliased()` solution
4. Test thoroughly to ensure functionality is preserved

## References

- SQLAlchemy Documentation on `aliased()`: https://docs.sqlalchemy.org/en/20/orm/queryguide/query.html#using-aliases
- SQLAlchemy Polymorphic Inheritance: https://docs.sqlalchemy.org/en/20/orm/inheritance.html
