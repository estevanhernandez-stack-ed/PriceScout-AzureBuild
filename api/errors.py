"""
PriceScout API - Error Handlers

RFC 7807 compliant error responses and helper functions.
"""

from enum import Enum
from typing import Optional, Dict, Any
from fastapi.responses import JSONResponse


class ProblemType(str, Enum):
    """RFC 7807 problem types."""
    BAD_REQUEST = "https://pricescout.com/problems/bad-request"
    UNAUTHORIZED = "https://pricescout.com/problems/unauthorized"
    FORBIDDEN = "https://pricescout.com/problems/forbidden"
    NOT_FOUND = "https://pricescout.com/problems/not-found"
    CONFLICT = "https://pricescout.com/problems/conflict"
    RATE_LIMITED = "https://pricescout.com/problems/rate-limited"
    INTERNAL_ERROR = "https://pricescout.com/problems/internal-error"
    SERVICE_UNAVAILABLE = "https://pricescout.com/problems/service-unavailable"
    VALIDATION_ERROR = "https://pricescout.com/problems/validation-error"
    PDF_GENERATION_ERROR = "https://pricescout.com/problems/pdf-generation-error"


def problem_response(
    type_: ProblemType,
    title: str,
    status: int,
    detail: Optional[str] = None,
    instance: Optional[str] = None,
    **kwargs: Any
) -> JSONResponse:
    """
    Create an RFC 7807 compliant problem response.
    
    Args:
        type_: Problem type URI
        title: Short summary of the problem
        status: HTTP status code
        detail: Optional detailed explanation
        instance: Optional URI reference to the specific occurrence
        **kwargs: Additional problem-specific fields
        
    Returns:
        JSONResponse with RFC 7807 format
    """
    problem = {
        "type": type_.value,
        "title": title,
        "status": status,
    }
    
    if detail:
        problem["detail"] = detail
    if instance:
        problem["instance"] = instance
        
    # Add any additional fields
    problem.update(kwargs)
    
    return JSONResponse(
        status_code=status,
        content=problem,
        headers={"Content-Type": "application/problem+json"}
    )


def validation_error(
    detail: str = "Request validation failed",
    errors: Optional[Dict[str, Any]] = None,
    instance: Optional[str] = None
) -> JSONResponse:
    """
    Create a validation error response.
    
    Args:
        detail: Error description
        errors: Dictionary of field-specific errors
        instance: Request path or identifier
        
    Returns:
        JSONResponse with validation error details
    """
    return problem_response(
        type_=ProblemType.VALIDATION_ERROR,
        title="Validation Error",
        status=422,
        detail=detail,
        instance=instance,
        errors=errors or {}
    )


def not_found_error(
    detail: str = "Resource not found",
    resource_type: Optional[str] = None,
    resource_id: Optional[Any] = None,
    instance: Optional[str] = None
) -> JSONResponse:
    """
    Create a not found error response.
    
    Args:
        detail: Error description
        resource_type: Type of resource (e.g., "Film", "Theater")
        resource_id: ID of the missing resource
        instance: Request path
        
    Returns:
        JSONResponse with not found error
    """
    kwargs = {}
    if resource_type:
        kwargs["resource_type"] = resource_type
    if resource_id is not None:
        kwargs["resource_id"] = resource_id
        
    return problem_response(
        type_=ProblemType.NOT_FOUND,
        title="Not Found",
        status=404,
        detail=detail,
        instance=instance,
        **kwargs
    )


def unauthorized_error(
    detail: str = "Authentication required",
    instance: Optional[str] = None,
    www_authenticate: Optional[str] = None
) -> JSONResponse:
    """
    Create an unauthorized error response.
    
    Args:
        detail: Error description
        instance: Request path
        www_authenticate: WWW-Authenticate header value
        
    Returns:
        JSONResponse with unauthorized error
    """
    headers = {}
    if www_authenticate:
        headers["WWW-Authenticate"] = www_authenticate
        
    response = problem_response(
        type_=ProblemType.UNAUTHORIZED,
        title="Unauthorized",
        status=401,
        detail=detail,
        instance=instance
    )
    
    if headers:
        for key, value in headers.items():
            response.headers[key] = value
            
    return response


def internal_error(
    detail: str = "An internal error occurred",
    instance: Optional[str] = None,
    error_id: Optional[str] = None
) -> JSONResponse:
    """
    Create an internal server error response.
    
    Args:
        detail: Error description
        instance: Request path
        error_id: Unique error identifier for tracking
        
    Returns:
        JSONResponse with internal error
    """
    kwargs = {}
    if error_id:
        kwargs["error_id"] = error_id
        
    return problem_response(
        type_=ProblemType.INTERNAL_ERROR,
        title="Internal Server Error",
        status=500,
        detail=detail,
        instance=instance,
        **kwargs
    )


def pdf_generation_error(
    detail: str = "Failed to generate PDF",
    instance: Optional[str] = None,
    error_message: Optional[str] = None
) -> JSONResponse:
    """
    Create a PDF generation error response.
    
    Args:
        detail: Error description
        instance: Request path
        error_message: Specific error from PDF generation
        
    Returns:
        JSONResponse with PDF generation error
    """
    kwargs = {}
    if error_message:
        kwargs["error_message"] = error_message
        
    return problem_response(
        type_=ProblemType.PDF_GENERATION_ERROR,
        title="PDF Generation Error",
        status=500,
        detail=detail,
        instance=instance,
        **kwargs
    )
