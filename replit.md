# Overview

CigarPriceScout is a price comparison web application that helps users find the lowest delivered prices for cigar boxes across multiple retailers. The application features intelligent search capabilities that normalize product names, calculate true delivered costs including shipping and tax, and provide affiliate links for purchases. Built with FastAPI and featuring a clean, responsive frontend, it aggregates data from CSV files containing retailer product listings and provides real-time price comparisons.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Frontend Architecture
- **Static HTML/CSS/JavaScript**: Simple, lightweight frontend served directly by FastAPI
- **Responsive Design**: Mobile-first approach with CSS Grid for layout
- **Progressive Enhancement**: Core functionality works without JavaScript, enhanced UX with JS
- **Real-time Search**: AJAX-based search with instant results and visual feedback chips

## Backend Architecture
- **FastAPI Framework**: Modern Python web framework for high-performance API development
- **Async/Await Pattern**: Full async support for database operations and HTTP requests
- **Modular Design**: Separated concerns with dedicated modules for normalization, shipping calculations, and affiliate links
- **CSV Data Adapters**: Flexible adapter pattern for ingesting retailer data from various CSV formats

## Data Management
- **SQLite Database**: Lightweight, file-based database with async support via aiosqlite
- **SQLAlchemy ORM**: Async ORM for database operations with proper connection pooling
- **Event Tracking**: Comprehensive analytics tracking for user searches and interactions
- **Price Point Storage**: Historical price data storage with unique constraints for data integrity

## Search and Normalization
- **Intent-Based Search**: Smart parsing that extracts brand, line, and size from natural language queries
- **Brand Recognition**: Configurable brand database for accurate product matching
- **Size Standardization**: Regex-based parsing for cigar dimensions (e.g., "6x52")
- **Fuzzy Matching**: Tolerant search that handles variations in product naming

## Pricing Engine
- **Delivered Cost Calculation**: True total cost including base price, shipping, and tax
- **Geographic Tax Calculation**: ZIP code to state mapping for accurate tax calculations
- **Retailer-Specific Shipping**: Configurable shipping costs per retailer
- **Real-time Comparison**: Live price comparison across all available retailers

## Business Logic
- **Box Filtering**: Logic to identify and filter only box quantities (typically 10, 12, 20, 24, 25, 50 count)
- **Stock Status**: Real-time inventory tracking and display
- **Affiliate Integration**: Commission Junction (CJ) affiliate link generation with proper encoding

# External Dependencies

## Core Framework Dependencies
- **FastAPI**: Web framework and API development
- **Uvicorn**: ASGI server for running the FastAPI application
- **SQLAlchemy**: Database ORM with async support
- **Pydantic**: Data validation and serialization

## Database
- **SQLite**: Primary data storage with aiosqlite for async operations
- **File-based Storage**: Data persistence without external database server requirements

## Affiliate Networks
- **Commission Junction (CJ)**: Affiliate marketing platform integration
- **Environment-based Configuration**: CJ Partner ID and Advertiser ID stored as secrets
- **Fallback Handling**: Graceful degradation when affiliate credentials are not configured

## Data Sources
- **CSV File Imports**: Retailer product catalogs in CSV format
- **Static File Serving**: Product data served from local static directory
- **Multi-retailer Support**: Designed for Famous Smoke Shop, Cigars International, and JR Cigars

## Development Tools
- **Python-dotenv**: Environment variable management for development
- **Jinja2**: Template engine (available for future template needs)
- **Replit Integration**: Configured for seamless deployment on Replit platform