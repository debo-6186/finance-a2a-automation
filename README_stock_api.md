# Stock Ticker API

A FastAPI-based REST API for managing stock tickers organized by type. The API provides endpoints to upsert, retrieve, and delete stock tickers, storing the data in a JSON file.

## Features

- **Upsert stock tickers**: Add or update stock tickers for a specific stock type
- **Retrieve stock tickers**: Get tickers for a specific type or all types
- **Delete stock types**: Remove a stock type and all its tickers
- **JSON storage**: Data is persisted in a `stock_data.json` file
- **RESTful API**: Clean REST endpoints with proper HTTP status codes
- **Input validation**: Uses Pydantic models for request/response validation

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Starting the Server

Run the API server:
```bash
python stock_api.py
```

The server will start on `http://localhost:8000`

### API Endpoints

#### 1. Upsert Stock Tickers
**POST** `/stock-tickers`

Add or update stock tickers for a specific stock type.

**Request Body:**
```json
{
    "stock_type": "tech",
    "stock_tickers": ["AAPL", "GOOGL", "MSFT", "TSLA"]
}
```

**Response:**
```json
{
    "message": "Successfully upserted 4 stock tickers for type 'tech'",
    "stock_type": "tech",
    "stock_tickers": ["AAPL", "GOOGL", "MSFT", "TSLA"]
}
```

#### 2. Get Stock Tickers by Type
**GET** `/stock-tickers/{stock_type}`

Retrieve stock tickers for a specific type.

**Example:** `GET /stock-tickers/tech`

**Response:**
```json
{
    "stock_type": "tech",
    "stock_tickers": ["AAPL", "GOOGL", "MSFT", "TSLA"]
}
```

#### 3. Get All Stock Tickers
**GET** `/stock-tickers`

Retrieve all stock types and their tickers.

**Response:**
```json
{
    "tech": ["AAPL", "GOOGL", "MSFT", "TSLA"],
    "finance": ["JPM", "BAC", "WFC"],
    "healthcare": ["JNJ", "PFE", "UNH"]
}
```

#### 4. Delete Stock Type
**DELETE** `/stock-tickers/{stock_type}`

Delete a stock type and all its tickers.

**Example:** `DELETE /stock-tickers/tech`

**Response:**
```json
{
    "message": "Successfully deleted stock type 'tech'",
    "deleted_tickers": ["AAPL", "GOOGL", "MSFT", "TSLA"]
}
```

#### 5. Health Check
**GET** `/health`

Check if the API is running.

**Response:**
```json
{
    "status": "healthy"
}
```

## Data Storage

The API stores data in a `stock_data.json` file in the following format:

```json
{
    "tech": ["AAPL", "GOOGL", "MSFT", "TSLA"],
    "finance": ["JPM", "BAC", "WFC"],
    "healthcare": ["JNJ", "PFE", "UNH"]
}
```

## Error Handling

The API includes comprehensive error handling:

- **400 Bad Request**: Invalid request data
- **404 Not Found**: Stock type not found
- **500 Internal Server Error**: Server-side errors

## Example Usage with curl

### Add stock tickers:
```bash
curl -X POST "http://localhost:8000/stock-tickers" \
     -H "Content-Type: application/json" \
     -d '{
       "stock_type": "tech",
       "stock_tickers": ["AAPL", "GOOGL", "MSFT", "TSLA"]
     }'
```

### Get stock tickers for a type:
```bash
curl "http://localhost:8000/stock-tickers/tech"
```

### Get all stock tickers:
```bash
curl "http://localhost:8000/stock-tickers"
```

### Delete a stock type:
```bash
curl -X DELETE "http://localhost:8000/stock-tickers/tech"
```

## API Documentation

Once the server is running, you can access the interactive API documentation at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc` 