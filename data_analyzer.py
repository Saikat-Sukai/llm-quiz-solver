import pandas as pd
import numpy as np
import json
import base64
from io import BytesIO, StringIO
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

class DataAnalyzer:
    """Helper class for data analysis tasks"""
    
    @staticmethod
    def parse_csv(content):
        """Parse CSV content into DataFrame"""
        try:
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            df = pd.read_csv(StringIO(content))
            logger.info(f"Parsed CSV: {df.shape[0]} rows, {df.shape[1]} columns")
            return df
        except Exception as e:
            logger.error(f"Error parsing CSV: {str(e)}")
            return None
    
    @staticmethod
    def parse_json(content):
        """Parse JSON content"""
        try:
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            data = json.loads(content)
            logger.info(f"Parsed JSON: {type(data)}")
            return data
        except Exception as e:
            logger.error(f"Error parsing JSON: {str(e)}")
            return None
    
    @staticmethod
    def analyze_dataframe(df, question):
        """Perform common analysis on DataFrame based on question keywords"""
        analysis = {
            'shape': df.shape,
            'columns': list(df.columns),
            'dtypes': df.dtypes.to_dict(),
            'summary': {}
        }
        
        question_lower = question.lower()
        
        # Sum operation
        if 'sum' in question_lower:
            for col in df.select_dtypes(include=[np.number]).columns:
                analysis['summary'][f'sum_{col}'] = float(df[col].sum())
        
        # Mean/average operation
        if any(word in question_lower for word in ['mean', 'average']):
            for col in df.select_dtypes(include=[np.number]).columns:
                analysis['summary'][f'mean_{col}'] = float(df[col].mean())
        
        # Count operation
        if 'count' in question_lower:
            analysis['summary']['row_count'] = len(df)
            for col in df.columns:
                if df[col].dtype == 'object':
                    analysis['summary'][f'unique_{col}'] = df[col].nunique()
        
        # Max/min operations
        if 'max' in question_lower or 'highest' in question_lower:
            for col in df.select_dtypes(include=[np.number]).columns:
                analysis['summary'][f'max_{col}'] = float(df[col].max())
        
        if 'min' in question_lower or 'lowest' in question_lower:
            for col in df.select_dtypes(include=[np.number]).columns:
                analysis['summary'][f'min_{col}'] = float(df[col].min())
        
        # Group by operations
        if 'group' in question_lower or 'by' in question_lower:
            # Try to identify grouping columns
            categorical_cols = df.select_dtypes(include=['object']).columns
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            
            if len(categorical_cols) > 0 and len(numeric_cols) > 0:
                try:
                    grouped = df.groupby(categorical_cols[0])[numeric_cols[0]].sum()
                    analysis['summary']['grouped'] = grouped.to_dict()
                except:
                    pass
        
        return analysis
    
    @staticmethod
    def create_chart(df, chart_type='bar', x_col=None, y_col=None):
        """Create a chart and return as base64 image"""
        try:
            plt.figure(figsize=(10, 6))
            
            if chart_type == 'bar' and x_col and y_col:
                df.plot(kind='bar', x=x_col, y=y_col, ax=plt.gca())
            elif chart_type == 'line' and x_col and y_col:
                df.plot(kind='line', x=x_col, y=y_col, ax=plt.gca())
            elif chart_type == 'pie' and x_col and y_col:
                df.set_index(x_col)[y_col].plot(kind='pie', ax=plt.gca())
            else:
                # Default: bar chart of first numeric column
                numeric_cols = df.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) > 0:
                    df[numeric_cols[0]].plot(kind='bar', ax=plt.gca())
            
            plt.tight_layout()
            
            # Save to buffer
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100)
            buffer.seek(0)
            plt.close()
            
            # Convert to base64
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            return f"data:image/png;base64,{image_base64}"
            
        except Exception as e:
            logger.error(f"Error creating chart: {str(e)}")
            return None
    
    @staticmethod
    def filter_dataframe(df, filters):
        """Apply filters to DataFrame
        
        filters: dict like {"column": "value"} or {"column": {"op": ">", "value": 10}}
        """
        try:
            filtered_df = df.copy()
            
            for col, condition in filters.items():
                if col not in df.columns:
                    continue
                
                if isinstance(condition, dict):
                    op = condition.get('op', '==')
                    value = condition.get('value')
                    
                    if op == '>':
                        filtered_df = filtered_df[filtered_df[col] > value]
                    elif op == '<':
                        filtered_df = filtered_df[filtered_df[col] < value]
                    elif op == '>=':
                        filtered_df = filtered_df[filtered_df[col] >= value]
                    elif op == '<=':
                        filtered_df = filtered_df[filtered_df[col] <= value]
                    elif op == '==':
                        filtered_df = filtered_df[filtered_df[col] == value]
                    elif op == '!=':
                        filtered_df = filtered_df[filtered_df[col] != value]
                else:
                    # Simple equality filter
                    filtered_df = filtered_df[filtered_df[col] == condition]
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"Error filtering DataFrame: {str(e)}")
            return df
    
    @staticmethod
    def aggregate_data(df, group_by, agg_dict):
        """Aggregate data by group
        
        group_by: column name or list of column names
        agg_dict: dict like {"column": "sum"} or {"column": ["sum", "mean"]}
        """
        try:
            result = df.groupby(group_by).agg(agg_dict)
            return result.reset_index()
        except Exception as e:
            logger.error(f"Error aggregating data: {str(e)}")
            return None
    
    @staticmethod
    def statistical_summary(df):
        """Generate statistical summary of DataFrame"""
        try:
            summary = {
                'shape': df.shape,
                'columns': list(df.columns),
                'numeric_summary': df.describe().to_dict(),
                'missing_values': df.isnull().sum().to_dict(),
                'duplicates': int(df.duplicated().sum())
            }
            return summary
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return None