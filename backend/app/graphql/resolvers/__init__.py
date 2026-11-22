"""GraphQL resolvers package.

Exports resolver groups wired to Ariadne schema:
- query_resolvers: Query type resolvers
- mutation_resolvers: Mutation type resolvers
- subscription_resolvers: Subscription type resolvers
"""

from app.graphql.resolvers.account import account_type_resolvers
from app.graphql.resolvers.mutation import mutation_resolvers
from app.graphql.resolvers.query import query_resolvers
from app.graphql.resolvers.subscription import subscription_resolvers

__all__ = [
    "query_resolvers",
    "mutation_resolvers",
    "subscription_resolvers",
    "account_type_resolvers",
]