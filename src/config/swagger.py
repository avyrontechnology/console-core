class SwaggerConfig:
    """Defines the JWT Bearer authentication scheme for Swagger."""

    jwt_auth_scheme = {
        "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }

    @staticmethod
    def get_swagger_config(app):
        """Configures JWT authentication for the Swagger UI."""
        app.openapi_schema = app.openapi()
        app.openapi_schema["components"][
            "securitySchemes"
        ] = SwaggerConfig.jwt_auth_scheme
        app.openapi_schema["security"] = [{"BearerAuth": []}]
        return app
