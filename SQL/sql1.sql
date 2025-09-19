select Layers.name, Layers.LayerId,  gfd.* from GridFilterDefinitions gfd 
left join GridColumns gc on gfd.GridFilterDefinitionId = gc.GridFilterDefinitionId
left join Layers on gc.LayerId = Layers.LayerId
WHERE IdField = 'localAuthorityId'
ORDER by Name

select * from GridFilterDefinitions WHERE IdField = 'localAuthorityId' or Store  = 'boundaries.LocalAuthorities'