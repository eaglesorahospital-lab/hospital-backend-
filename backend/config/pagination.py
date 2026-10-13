from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination for Hospital Platform REST API endpoints.
    Provides page number navigation with customizable page sizes.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100
