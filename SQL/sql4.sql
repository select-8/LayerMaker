-- Fix for DirectionalCode / DirectionalId
UPDATE GridColumns
SET GridFilterDefinitionId = NULL,
    FilterType = 'number'
WHERE ColumnName = 'LocalAuthorityId'
  AND GridFilterDefinitionId = 5;

UPDATE GridColumns
SET GridFilterDefinitionId = 5,
    FilterType = 'list'
WHERE ColumnName = 'LocalAuthority';

UPDATE GridColumns
SET GridFilterDefinitionId = 5,
    FilterType = 'list'
WHERE GridColumnId = 22 AND LayerId = 3;
