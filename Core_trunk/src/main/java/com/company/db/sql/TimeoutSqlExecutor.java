package com.company.db.sql;

import com.company.db.DbClient;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;


public final class TimeoutSqlExecutor {

    private static final Logger log = LogManager.getLogger(TimeoutSqlExecutor.class);


    public static final int UNLIMITED = 0;

    private final DbClient db;
    private final int      timeoutSeconds;


    public TimeoutSqlExecutor(DbClient db) {
        this(db, UNLIMITED);
    }


    public TimeoutSqlExecutor(DbClient db, int timeoutSeconds) {
        if (db == null) throw new IllegalArgumentException("db must not be null");
        if (timeoutSeconds < 0) throw new IllegalArgumentException("timeoutSeconds must be >= 0");
        this.db             = db;
        this.timeoutSeconds = timeoutSeconds;
    }

    public int timeoutSeconds() { return timeoutSeconds; }


    public void execute(String sql) throws SQLException {
        if (timeoutSeconds == UNLIMITED) {
            db.execute(sql);
            return;
        }

        Connection connection = null;
        boolean restoreAutoCommit = false;
        try {
            connection = db.getConnection();
            restoreAutoCommit = connection.getAutoCommit();
            if (restoreAutoCommit) {
                connection.setAutoCommit(false);
            }

            try (Statement st = connection.createStatement()) {
                st.setQueryTimeout(timeoutSeconds);
                st.execute("SET LOCAL lock_timeout = '5s'");
                st.execute("SET LOCAL statement_timeout = '" + (timeoutSeconds * 1000L) + "ms'");
                st.execute(sql);
            }

            if (restoreAutoCommit) {
                connection.commit();
            }
        } catch (SQLException ex) {
            if (connection != null) {
                try { connection.rollback(); }
                catch (Exception rollbackEx) {
                    log.error("rollback after execute failure also failed", rollbackEx);
                }
            }
            throw ex;
        } finally {
            if (connection != null) {
                try { connection.setAutoCommit(restoreAutoCommit); } catch (Exception ignored) {  }
                try { connection.close(); } catch (Exception ignored) {  }
            }
        }
    }
}
